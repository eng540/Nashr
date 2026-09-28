"""Static and behavioural guards for the central Gemini policy.

``test_no_direct_generate_content_calls_outside_central_policy`` is the hard
rule: every ``client.models.generate_content`` call in the production package
must go through ``app.adapters.gemini_policy``. The remaining tests pin the
unified chain resolution, classification, retry/backoff, failover, original
error propagation and canonical log events.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from app.adapters.gemini_policy import (
    DEFAULT_GEMINI_MODELS,
    GEMINI_AUTH_ERROR,
    GEMINI_INVALID_ARGUMENT,
    GEMINI_NETWORK_ERROR,
    GEMINI_QUOTA_EXCEEDED,
    GEMINI_RATE_LIMITED,
    GEMINI_SERVER_ERROR,
    RetryPolicy,
    classify_gemini_error,
    generate_content,
    parse_model_chain,
    resolve_model_chain,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "app"
POLICY_FILE = APP_ROOT / "adapters" / "gemini_policy.py"


# ---------------------------------------------------------------------------
# Static protection rule
# ---------------------------------------------------------------------------


def _generate_content_calls(path: Path) -> list[int]:
    """Return the line numbers of direct ``*.generate_content(...)`` calls."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "generate_content"
        ):
            lines.append(node.lineno)
    return sorted(lines)


def test_no_direct_generate_content_calls_outside_central_policy() -> None:
    """No production layer may call ``generate_content`` outside the policy."""
    offenders: dict[str, list[int]] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.resolve() == POLICY_FILE.resolve():
            continue
        lines = _generate_content_calls(path)
        if lines:
            offenders[str(path.relative_to(REPO_ROOT))] = lines
    assert offenders == {}, f"direct generate_content calls found: {offenders}"


def test_central_policy_owns_the_only_generate_content_call() -> None:
    """Keep the rule non-vacuous: the policy module is the one allowed caller."""
    assert _generate_content_calls(POLICY_FILE)


# ---------------------------------------------------------------------------
# Chain resolution
# ---------------------------------------------------------------------------


def test_single_model_value_is_a_one_element_chain() -> None:
    assert parse_model_chain("gemini-x") == ("gemini-x",)


def test_comma_separated_value_is_an_ordered_cascade() -> None:
    assert parse_model_chain("gemini-a, gemini-b ,gemini-c") == ("gemini-a", "gemini-b", "gemini-c")


def test_chain_is_de_duplicated_and_blank_segments_ignored() -> None:
    assert parse_model_chain("a,,a, b") == ("a", "b")


def test_missing_or_empty_model_falls_back_to_the_default_chain() -> None:
    assert parse_model_chain(None) == DEFAULT_GEMINI_MODELS
    assert parse_model_chain("") == DEFAULT_GEMINI_MODELS
    assert parse_model_chain("   ") == DEFAULT_GEMINI_MODELS


def test_explicit_models_win_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "env-a,env-b")
    assert resolve_model_chain("explicit") == ("explicit",)
    assert resolve_model_chain(None) == ("env-a", "env-b")


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class _StatusError(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__(f"provider status {status}")
        self.status_code = status


class _TransientError(RuntimeError):
    pass


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (429, GEMINI_RATE_LIMITED),
        (401, GEMINI_AUTH_ERROR),
        (403, GEMINI_AUTH_ERROR),
        (400, GEMINI_INVALID_ARGUMENT),
        (500, GEMINI_SERVER_ERROR),
        (503, GEMINI_SERVER_ERROR),
    ],
)
def test_status_classification(status: int, code: str) -> None:
    assert classify_gemini_error(_StatusError(status))[0] == code


def test_transient_codes_are_retryable_and_permanent_are_not() -> None:
    assert classify_gemini_error(_StatusError(503))[1] is True
    assert classify_gemini_error(_StatusError(429))[1] is True
    assert classify_gemini_error(_StatusError(400))[1] is False
    assert classify_gemini_error(_StatusError(401))[1] is False


def test_unstructured_quota_message_stays_permanent() -> None:
    """Regression guard for the pre-existing quota classification contract."""
    code, retryable = classify_gemini_error(RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"))
    assert code == GEMINI_QUOTA_EXCEEDED
    assert retryable is False


def test_unstructured_transient_messages_are_retryable() -> None:
    assert classify_gemini_error(RuntimeError("503 Service Unavailable"))[0] == GEMINI_SERVER_ERROR
    assert classify_gemini_error(RuntimeError("503 Service Unavailable"))[1] is True
    assert classify_gemini_error(ConnectionError("connection reset"))[0] == GEMINI_NETWORK_ERROR
    assert classify_gemini_error(ConnectionError("connection reset"))[1] is True


# ---------------------------------------------------------------------------
# Retry + failover execution
# ---------------------------------------------------------------------------


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


def _policy(max_attempts: int = 2) -> RetryPolicy:
    return RetryPolicy(max_attempts=max_attempts)


def test_transient_failure_is_retried_then_succeeds() -> None:
    client = _FakeClient([_TransientError("500 boom"), "ok"])
    sleeps: list[float] = []
    result = generate_content(
        client,
        contents=["prompt"],
        models="m1",
        retry_policy=_policy(2),
        sleep=sleeps.append,
    )
    assert result == "ok"
    assert [call["model"] for call in client.models.calls] == ["m1", "m1"]
    assert sleeps == [_policy(2).delay_for(1)]


def test_exhausted_model_fails_over_to_the_next_model() -> None:
    client = _FakeClient([_TransientError("503 a"), _TransientError("503 b"), "ok"])
    sleeps: list[float] = []
    result = generate_content(
        client,
        contents=["prompt"],
        models="m1,m2",
        retry_policy=_policy(2),
        sleep=sleeps.append,
    )
    assert result == "ok"
    assert [call["model"] for call in client.models.calls] == ["m1", "m1", "m2"]
    assert len(sleeps) == 1


def test_permanent_error_is_raised_without_retry_or_failover() -> None:
    client = _FakeClient([_StatusError(400), "unused"])
    with pytest.raises(_StatusError):
        generate_content(client, contents=["prompt"], models="m1,m2", retry_policy=_policy(2), sleep=lambda _: None)
    assert [call["model"] for call in client.models.calls] == ["m1"]


def test_attempt_and_failover_counts_match_the_policy() -> None:
    failures = [_TransientError(f"503 attempt {index}") for index in range(6)]
    client = _FakeClient(list(failures))
    with pytest.raises(_TransientError) as info:
        generate_content(
            client,
            contents=["prompt"],
            models="m1,m2,m3",
            retry_policy=_policy(2),
            sleep=lambda _: None,
        )
    assert info.value is failures[-1]
    assert [call["model"] for call in client.models.calls] == ["m1", "m1", "m2", "m2", "m3", "m3"]


def test_exhausted_chain_raises_the_real_original_error() -> None:
    original = _StatusError(503)
    client = _FakeClient([_StatusError(503), original])
    with pytest.raises(_StatusError) as info:
        generate_content(client, contents=["prompt"], models="m1,m2", retry_policy=_policy(1), sleep=lambda _: None)
    assert info.value is original


def test_list_environment_value_is_used_by_every_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "m1,m2")
    client = _FakeClient([_TransientError("503 a"), "ok"])
    result = generate_content(client, contents=["prompt"], retry_policy=_policy(1), sleep=lambda _: None)
    assert result == "ok"
    assert [call["model"] for call in client.models.calls] == ["m1", "m2"]


# ---------------------------------------------------------------------------
# Canonical log events
# ---------------------------------------------------------------------------


def test_canonical_events_are_emitted_across_retry_and_failover(caplog: pytest.LogCaptureFixture) -> None:
    client = _FakeClient([_TransientError("503 a"), _TransientError("503 b"), "ok"])
    with caplog.at_level(logging.INFO, logger="app.adapters.gemini_policy"):
        generate_content(client, contents=["prompt"], models="m1,m2", retry_policy=_policy(2), sleep=lambda _: None)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for event in (
        "GEMINI_CHAIN_CONFIGURED",
        "GEMINI_ATTEMPT_START",
        "GEMINI_ATTEMPT_SUCCESS",
        "GEMINI_TRANSIENT_ERROR",
        "GEMINI_RETRY_BACKOFF",
        "GEMINI_MODEL_FAILOVER",
    ):
        assert f"event={event}" in logged


def test_permanent_error_event_is_emitted(caplog: pytest.LogCaptureFixture) -> None:
    client = _FakeClient([_StatusError(400)])
    with caplog.at_level(logging.INFO, logger="app.adapters.gemini_policy"):
        with pytest.raises(_StatusError):
            generate_content(client, contents=["prompt"], models="m1", retry_policy=_policy(2), sleep=lambda _: None)
    assert any("event=GEMINI_PERMANENT_ERROR" in record.getMessage() for record in caplog.records)