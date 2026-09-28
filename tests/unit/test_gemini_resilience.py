"""Resilience and HTTP-mapping coverage for the central Gemini policy."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from app.adapters.gemini_policy import (
    GEMINI_AUTH_ERROR,
    GEMINI_DEADLINE_EXCEEDED,
    GEMINI_FILE_TIMEOUT,
    GEMINI_INVALID_ARGUMENT,
    GEMINI_NETWORK_ERROR,
    GEMINI_QUOTA_EXCEEDED,
    GEMINI_RATE_LIMITED,
    GEMINI_SERVER_ERROR,
    GeminiOperationError,
    RetryPolicy,
    gemini_http_options,
    generate_content,
    http_status_for,
    retry_after_seconds,
)


class _StatusError(RuntimeError):
    def __init__(self, status: int, headers: dict | None = None) -> None:
        super().__init__(f"provider status {status}")
        self.status_code = status
        if headers is not None:
            self.response = SimpleNamespace(headers=headers)


class _TransientError(RuntimeError):
    pass


class _FakeModels:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.models = _FakeModels(outcomes)


class _Clock:
    """Deterministic monotonic-like clock that advances per call."""

    def __init__(self, values: list[float], fallback: float = 0.0) -> None:
        self._values = list(values)
        self._last = fallback

    def __call__(self) -> float:
        if self._values:
            self._last = self._values.pop(0)
        return self._last


# ---------------------------------------------------------------------------
# HTTP mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (GEMINI_SERVER_ERROR, 503),
        (GEMINI_NETWORK_ERROR, 503),
        (GEMINI_FILE_TIMEOUT, 503),
        (GEMINI_RATE_LIMITED, 429),
        (GEMINI_QUOTA_EXCEEDED, 429),
        (GEMINI_AUTH_ERROR, 401),
        (GEMINI_INVALID_ARGUMENT, 400),
        (GEMINI_DEADLINE_EXCEEDED, 504),
    ],
)
def test_http_status_mapping(code: str, status: int) -> None:
    assert http_status_for(code) == status


def test_unknown_code_maps_to_500() -> None:
    assert http_status_for("GEMINI_SOMETHING_ELSE") == 500


def test_retry_after_is_read_from_the_response_headers() -> None:
    exc = _StatusError(503, headers={"retry-after": "7"})
    assert retry_after_seconds(exc) == 7.0


def test_retry_after_is_none_without_a_header() -> None:
    assert retry_after_seconds(_StatusError(503)) is None


# ---------------------------------------------------------------------------
# SDK retry authority
# ---------------------------------------------------------------------------


def test_sdk_retries_are_disabled_in_the_shared_http_options() -> None:
    pytest.importorskip("google.genai")
    options = gemini_http_options()
    assert options is not None
    assert options.retry_options is not None
    assert options.retry_options.attempts == 1


# ---------------------------------------------------------------------------
# Total budget
# ---------------------------------------------------------------------------


def test_budget_exhausted_before_first_attempt_raises_a_clear_error() -> None:
    client = _FakeClient(["unused"])
    policy = RetryPolicy(max_attempts=2, total_timeout_seconds=10.0)
    with pytest.raises(GeminiOperationError) as info:
        generate_content(
            client,
            contents=["prompt"],
            models="m1,m2",
            retry_policy=policy,
            sleep=lambda _: None,
            clock=_Clock([0.0, 100.0], fallback=100.0),
        )
    assert info.value.code == GEMINI_DEADLINE_EXCEEDED
    assert client.models.calls == []


def test_budget_exhausted_between_attempts_raises_the_original_error() -> None:
    original = _TransientError("503 high demand")
    client = _FakeClient([original, "unused"])
    policy = RetryPolicy(max_attempts=2, total_timeout_seconds=10.0)
    with pytest.raises(_TransientError) as info:
        generate_content(
            client,
            contents=["prompt"],
            models="m1,m2",
            retry_policy=policy,
            sleep=lambda _: None,
            clock=_Clock([0.0, 1.0, 11.0], fallback=11.0),
        )
    assert info.value is original
    assert [call["model"] for call in client.models.calls] == ["m1"]


def test_budget_exhaustion_event_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    policy = RetryPolicy(max_attempts=2, total_timeout_seconds=10.0)
    client = _FakeClient([_TransientError("503"), "unused"])
    with caplog.at_level(logging.INFO, logger="app.adapters.gemini_policy"):
        with pytest.raises(_TransientError):
            generate_content(
                client,
                contents=["prompt"],
                models="m1,m2",
                retry_policy=policy,
                sleep=lambda _: None,
                clock=_Clock([0.0, 1.0, 11.0], fallback=11.0),
            )
    assert any("event=GEMINI_BUDGET_EXHAUSTED" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# Retry-After honouring
# ---------------------------------------------------------------------------


def test_retry_after_extends_the_backoff_delay() -> None:
    exc = _StatusError(503, headers={"retry-after": "5"})
    client = _FakeClient([exc, "ok"])
    sleeps: list[float] = []
    policy = RetryPolicy(max_attempts=2, backoff_min_seconds=2.0, backoff_max_seconds=10.0, total_timeout_seconds=0)
    result = generate_content(
        client,
        contents=["prompt"],
        models="m1",
        retry_policy=policy,
        sleep=sleeps.append,
    )
    assert result == "ok"
    assert sleeps == [5.0]


def test_backoff_is_clamped_to_the_policy_maximum() -> None:
    exc = _StatusError(503, headers={"retry-after": "120"})
    client = _FakeClient([exc, "ok"])
    sleeps: list[float] = []
    policy = RetryPolicy(max_attempts=2, backoff_min_seconds=2.0, backoff_max_seconds=10.0, total_timeout_seconds=0)
    generate_content(client, contents=["prompt"], models="m1", retry_policy=policy, sleep=sleeps.append)
    assert sleeps == [10.0]


# ---------------------------------------------------------------------------
# HTTP exception handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_maps_a_provider_503_to_http_503() -> None:
    from app.main import gemini_exception_handler

    request = SimpleNamespace(url=SimpleNamespace(path="/benchmark/run/x"))
    response = await gemini_exception_handler(request, _StatusError(503))
    payload = json.loads(bytes(response.body))

    assert response.status_code == 503
    assert payload["code"] == GEMINI_SERVER_ERROR
    assert payload["retryable"] is True


@pytest.mark.asyncio
async def test_handler_maps_a_provider_400_to_http_400_without_retry() -> None:
    from app.main import gemini_exception_handler

    request = SimpleNamespace(url=SimpleNamespace(path="/draft"))
    response = await gemini_exception_handler(request, _StatusError(400))
    payload = json.loads(bytes(response.body))

    assert response.status_code == 400
    assert payload["code"] == GEMINI_INVALID_ARGUMENT
    assert payload["retryable"] is False


@pytest.mark.asyncio
async def test_handler_forwards_the_retry_after_header() -> None:
    from app.main import gemini_exception_handler

    request = SimpleNamespace(url=SimpleNamespace(path="/benchmark/run/x"))
    response = await gemini_exception_handler(request, _StatusError(503, headers={"retry-after": "9"}))

    assert response.headers["retry-after"] == "9"