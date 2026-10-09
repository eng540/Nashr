"""Central Google Gemini capability policy for Nashr.

This module is the single source of truth for every Gemini interaction in the
system. It owns, and only it owns:

- model-chain resolution from ``GEMINI_MODEL`` (a single model, or a
  comma-separated failover cascade);
- transient-vs-permanent error classification;
- the unified retry/backoff policy;
- failover from one model to the next when a model is exhausted;
- the one and only ``client.models.generate_content`` execution path;
- canonical, identically-shaped log events for every calling layer.

Every adapter (editorial drafting, book mapping, bounded material discovery,
flat extraction, the benchmark route) consumes :func:`generate_content` /
:func:`generate_content_async`. No other module may call
``client.models.generate_content`` directly; ``tests/unit/test_gemini_policy_guard.py``
enforces that rule statically.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Keep a guarded import so the pure policy module stays importable even when the
# optional classification hints are unavailable; the HTTP status of a structured
# error remains the primary signal.
try:  # pragma: no cover - exercised implicitly by the installed dependency
    from google.genai.errors import APIError as _GoogleAPIError
    from google.genai.errors import ServerError as _GoogleServerError
except Exception:  # pragma: no cover - defensive fallback only
    _GoogleAPIError = None  # type: ignore[assignment]
    _GoogleServerError = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Defaults and the environment contract
# ---------------------------------------------------------------------------

DEFAULT_GEMINI_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
)
# Legacy singular alias kept for backward-compatible imports.
DEFAULT_GEMINI_MODEL = DEFAULT_GEMINI_MODELS[0]

GEMINI_MODEL_ENV = "GEMINI_MODEL"
GEMINI_RETRY_MAX_ATTEMPTS_ENV = "GEMINI_RETRY_MAX_ATTEMPTS"
GEMINI_RETRY_BACKOFF_MIN_ENV = "GEMINI_RETRY_BACKOFF_MIN_SECONDS"
GEMINI_RETRY_BACKOFF_MAX_ENV = "GEMINI_RETRY_BACKOFF_MAX_SECONDS"
GEMINI_RETRY_BACKOFF_MULTIPLIER_ENV = "GEMINI_RETRY_BACKOFF_MULTIPLIER"
GEMINI_TOTAL_TIMEOUT_ENV = "GEMINI_TOTAL_TIMEOUT_SECONDS"
GEMINI_SDK_RETRY_ATTEMPTS_ENV = "GEMINI_SDK_RETRY_ATTEMPTS"
GEMINI_HTTP_TIMEOUT_MS_ENV = "GEMINI_HTTP_TIMEOUT_MS"

DEFAULT_RETRY_MAX_ATTEMPTS = 2
DEFAULT_RETRY_BACKOFF_MIN_SECONDS = 2.0
DEFAULT_RETRY_BACKOFF_MAX_SECONDS = 10.0
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 2.0
# Total wall-clock budget for one full chain walk. 0 disables the budget.
DEFAULT_TOTAL_TIMEOUT_SECONDS = 120.0
# The google-genai SDK must not retry on its own: the cascade below is the only
# retry authority (otherwise one policy attempt hides several SDK attempts).
DEFAULT_SDK_RETRY_ATTEMPTS = 1
DEFAULT_HTTP_TIMEOUT_MS = 90_000


# ---------------------------------------------------------------------------
# Stable, cross-layer error codes
# ---------------------------------------------------------------------------

GEMINI_FILE_TIMEOUT = "GEMINI_FILE_TIMEOUT"
GEMINI_QUOTA_EXCEEDED = "GEMINI_QUOTA_EXCEEDED"
GEMINI_RATE_LIMITED = "GEMINI_RATE_LIMITED"
GEMINI_AUTH_ERROR = "GEMINI_AUTH_ERROR"
GEMINI_FILE_NOT_FOUND = "GEMINI_FILE_NOT_FOUND"
GEMINI_INVALID_ARGUMENT = "GEMINI_INVALID_ARGUMENT"
GEMINI_SERVER_ERROR = "GEMINI_SERVER_ERROR"
GEMINI_NETWORK_ERROR = "GEMINI_NETWORK_ERROR"
GEMINI_API_ERROR = "GEMINI_API_ERROR"
GEMINI_EMPTY_RESPONSE = "GEMINI_EMPTY_RESPONSE"
GEMINI_DEADLINE_EXCEEDED = "GEMINI_DEADLINE_EXCEEDED"


class GeminiOperationError(RuntimeError):
    """Normalized Gemini failure carrying a stable application error code.

    The class lives here so that every layer classifies and wraps Gemini
    failures from the same definition; ``app.adapters.extraction.gemini``
    re-exports it for backward compatibility.
    """

    def __init__(self, code: str, message: str, retryable: bool = False, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.cause = cause


# ---------------------------------------------------------------------------
# Retry policy (the only place where retry constants are defined)
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class RetryPolicy:
    """The unified retry/backoff policy applied to every Gemini call.

    ``max_attempts`` is the number of attempts *per model*. When a model
    exhausts its attempts with a transient failure the cascade fails over to
    the next model in the chain.
    """

    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    backoff_min_seconds: float = DEFAULT_RETRY_BACKOFF_MIN_SECONDS
    backoff_max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS
    backoff_multiplier: float = DEFAULT_RETRY_BACKOFF_MULTIPLIER
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("RetryPolicy.max_attempts must be at least 1.")

    @classmethod
    def from_env(cls) -> "RetryPolicy":
        """Build the policy from the environment, falling back to the defaults."""
        return cls(
            max_attempts=_env_int(GEMINI_RETRY_MAX_ATTEMPTS_ENV, DEFAULT_RETRY_MAX_ATTEMPTS, minimum=1),
            backoff_min_seconds=_env_float(GEMINI_RETRY_BACKOFF_MIN_ENV, DEFAULT_RETRY_BACKOFF_MIN_SECONDS),
            backoff_max_seconds=_env_float(GEMINI_RETRY_BACKOFF_MAX_ENV, DEFAULT_RETRY_BACKOFF_MAX_SECONDS),
            backoff_multiplier=_env_float(GEMINI_RETRY_BACKOFF_MULTIPLIER_ENV, DEFAULT_RETRY_BACKOFF_MULTIPLIER),
            total_timeout_seconds=_env_float(GEMINI_TOTAL_TIMEOUT_ENV, DEFAULT_TOTAL_TIMEOUT_SECONDS, minimum=0.0),
        )

    def delay_for(self, attempt_number: int) -> float:
        """Return the exponential backoff delay after a failed attempt.

        ``attempt_number`` is the 1-based attempt that just failed. The delay is
        clamped to ``[backoff_min_seconds, backoff_max_seconds]``.
        """
        if attempt_number < 1:
            return 0.0
        raw = self.backoff_min_seconds * (self.backoff_multiplier ** (attempt_number - 1))
        return min(self.backoff_max_seconds, raw)


# ---------------------------------------------------------------------------
# Model chain resolution (the only place that reads GEMINI_MODEL)
# ---------------------------------------------------------------------------


def parse_model_chain(raw: str | None) -> tuple[str, ...]:
    """Parse a ``GEMINI_MODEL`` value into an ordered, de-duplicated chain.

    ``None`` or an empty value falls back to :data:`DEFAULT_GEMINI_MODELS`. A
    single model is a one-element chain; a comma-separated value is a failover
    cascade. Whitespace and empty segments are ignored.
    """
    if raw is None:
        return DEFAULT_GEMINI_MODELS
    models: list[str] = []
    for part in str(raw).split(","):
        candidate = part.strip()
        if candidate and candidate not in models:
            models.append(candidate)
    return tuple(models) if models else DEFAULT_GEMINI_MODELS


def resolve_model_chain(explicit: str | Sequence[str] | None = None) -> tuple[str, ...]:
    """Resolve the effective model chain.

    An explicit value (constructor override) wins over the environment; otherwise
    ``GEMINI_MODEL`` is read, and when it is unset the default chain applies.
    """
    if explicit is None:
        return parse_model_chain(os.getenv(GEMINI_MODEL_ENV))
    if isinstance(explicit, str):
        return parse_model_chain(explicit)
    return parse_model_chain(",".join(str(model) for model in explicit))


# ---------------------------------------------------------------------------
# Error classification (the only place that decides transient vs permanent)
# ---------------------------------------------------------------------------


def _status_code(exc: Exception) -> int | None:
    """Extract an HTTP status code from a structured provider exception."""
    for attribute in ("status_code", "code"):
        value = getattr(exc, attribute, None)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            candidate = getattr(value, "value", None)
            if isinstance(candidate, int):
                return candidate
    return None


def _classify_status(status: int) -> tuple[str, bool] | None:
    if status == 429:
        return GEMINI_RATE_LIMITED, True
    if status in (401, 403):
        return GEMINI_AUTH_ERROR, False
    if status == 404:
        return GEMINI_FILE_NOT_FOUND, False
    if status == 400:
        return GEMINI_INVALID_ARGUMENT, False
    if status == 408:
        return GEMINI_NETWORK_ERROR, True
    if 500 <= status < 600:
        return GEMINI_SERVER_ERROR, True
    if 400 <= status < 500:
        return GEMINI_API_ERROR, False
    return None


def _classify_message(exc: Exception) -> tuple[str, bool]:
    text = str(exc).lower()
    if "resource_exhausted" in text or "quota" in text:
        return GEMINI_QUOTA_EXCEEDED, False
    if "rate limit" in text or "too many requests" in text or "429" in text:
        return GEMINI_RATE_LIMITED, True
    if "unauthenticated" in text or "permission denied" in text or "401" in text or "403" in text:
        return GEMINI_AUTH_ERROR, False
    if "not found" in text or "404" in text:
        return GEMINI_FILE_NOT_FOUND, False
    if "invalid argument" in text or "invalid_argument" in text or "400" in text:
        return GEMINI_INVALID_ARGUMENT, False
    if any(
        word in text
        for word in (
            "503",
            "500",
            "502",
            "504",
            "unavailable",
            "high demand",
            "internal error",
            "bad gateway",
            "deadline exceeded",
        )
    ):
        return GEMINI_SERVER_ERROR, True
    if isinstance(exc, (ConnectionError, OSError)) or "timeout" in text or "connection" in text:
        return GEMINI_NETWORK_ERROR, True
    return GEMINI_API_ERROR, False


def classify_gemini_error(exc: Exception) -> tuple[str, bool]:
    """Return ``(code, retryable)`` for any Gemini-facing exception.

    The HTTP status of a structured provider error is authoritative; message
    heuristics only apply to unstructured failures. A ``429`` raised by the
    provider is therefore retried (and then failed over) even when its message
    mentions quotas, while an unstructured quota message remains non-retryable.
    """
    if isinstance(exc, GeminiOperationError):
        return exc.code, exc.retryable
    if isinstance(exc, TimeoutError):
        return GEMINI_FILE_TIMEOUT, True

    status = _status_code(exc)
    if status is not None:
        classified = _classify_status(status)
        if classified is not None:
            return classified

    if _GoogleServerError is not None and isinstance(exc, _GoogleServerError):
        return GEMINI_SERVER_ERROR, True

    return _classify_message(exc)


def is_transient_error(exc: Exception) -> bool:
    """Return ``True`` when a failure is worth retrying or failing over."""
    return classify_gemini_error(exc)[1]


# ---------------------------------------------------------------------------
# Client construction (the only place that builds a google-genai client)
# ---------------------------------------------------------------------------


def gemini_http_options() -> Any:
    """Return the shared SDK HTTP options, or ``None`` when unavailable.

    The google-genai SDK retries retryable statuses on its own (5 attempts by
    default). That silently multiplies every retry made by this policy, so the
    SDK retry count is pinned to 1 and the cascade here is the only retry
    authority. Set ``GEMINI_SDK_RETRY_ATTEMPTS`` to raise it deliberately.
    """
    try:
        from google.genai import types
    except Exception:  # pragma: no cover - defensive fallback only
        return None
    attempts = _env_int(GEMINI_SDK_RETRY_ATTEMPTS_ENV, DEFAULT_SDK_RETRY_ATTEMPTS, minimum=1)
    timeout_ms = _env_int(GEMINI_HTTP_TIMEOUT_MS_ENV, DEFAULT_HTTP_TIMEOUT_MS, minimum=1000)
    try:
        return types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=attempts),
            timeout=timeout_ms,
        )
    except Exception:  # pragma: no cover - defensive fallback only
        return None


def create_gemini_client(api_key: str | None = None) -> Any:
    """Build the single, policy-configured Gemini client used by every layer."""
    from google import genai

    options = gemini_http_options()
    if options is None:
        return genai.Client(api_key=api_key)
    return genai.Client(api_key=api_key, http_options=options)


# ---------------------------------------------------------------------------
# HTTP mapping for provider failures
# ---------------------------------------------------------------------------

_HTTP_STATUS_BY_CODE: dict[str, int] = {
    GEMINI_AUTH_ERROR: 401,
    GEMINI_INVALID_ARGUMENT: 400,
    GEMINI_FILE_NOT_FOUND: 404,
    GEMINI_RATE_LIMITED: 429,
    GEMINI_QUOTA_EXCEEDED: 429,
    GEMINI_FILE_TIMEOUT: 503,
    GEMINI_SERVER_ERROR: 503,
    GEMINI_NETWORK_ERROR: 503,
    GEMINI_DEADLINE_EXCEEDED: 504,
}


def http_status_for(code: str) -> int:
    """Map a stable Gemini error code to the HTTP status the caller should see."""
    return _HTTP_STATUS_BY_CODE.get(code, 500)


def retry_after_seconds(exc: Exception) -> float | None:
    """Read a retry delay from HTTP headers or Gemini's structured error body."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(exc, "headers", None)
    if headers is not None:
        try:
            raw = headers.get("retry-after") or headers.get("Retry-After")
        except Exception:  # pragma: no cover - defensive fallback only
            raw = None
        if raw is not None:
            try:
                return max(0.0, float(str(raw).strip()))
            except (TypeError, ValueError):
                pass

    # Google API errors may carry google.rpc.RetryInfo in details rather than
    # an HTTP Retry-After header. SDK versions expose the response body through
    # different attributes, so inspect structured details and the message.
    candidates: list[Any] = [
        getattr(exc, "details", None),
        getattr(exc, "message", None),
        str(exc),
    ]
    if response is not None:
        for attribute in ("text", "content"):
            value = getattr(response, attribute, None)
            if value:
                candidates.append(value)
        json_method = getattr(response, "json", None)
        if callable(json_method):
            try:
                candidates.append(json_method())
            except Exception:
                pass

    def find_retry_delay(value: Any) -> float | None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key).replace("_", "").lower() in {"retrydelay", "retryafter"}:
                    parsed = parse_duration(child)
                    if parsed is not None:
                        return parsed
                nested = find_retry_delay(child)
                if nested is not None:
                    return nested
        elif isinstance(value, (list, tuple)):
            for child in value:
                nested = find_retry_delay(child)
                if nested is not None:
                    return nested
        elif isinstance(value, str):
            # Covers protobuf duration strings (e.g. "13.8s") and the
            # human-readable quota message ("Please retry in 13.8s").
            match = re.search(r"(?:retry(?:\s+in)?|retryDelay\s*[=:]?\s*[\"']?)(?:\s*[:=]?\s*[\"']?)(\d+(?:\.\d+)?)\s*s", value, re.IGNORECASE)
            if match:
                return max(0.0, float(match.group(1)))
            stripped = value.strip()
            duration = re.fullmatch(r"(\\d+(?:\\.\\d+)?)s", stripped)
            if duration:
                return max(0.0, float(duration.group(1)))
        return None

    def parse_duration(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
        if isinstance(value, str):
            stripped = value.strip()
            duration = re.fullmatch(r"(\\d+(?:\\.\\d+)?)s", stripped)
            if duration:
                return max(0.0, float(duration.group(1)))
            try:
                return max(0.0, float(stripped))
            except ValueError:
                return None
        return None

    for candidate in candidates:
        result = find_retry_delay(candidate)
        if result is not None:
            return result
    return None

# ---------------------------------------------------------------------------
# Canonical log events (identical field names and event names in every layer)
# ---------------------------------------------------------------------------


def _log_event(level: int, event: str, **fields: Any) -> None:
    detail = " ".join(f"{name}={value}" for name, value in fields.items() if value is not None)
    logger.log(level, "event=%s%s", event, f" {detail}" if detail else "")


# ---------------------------------------------------------------------------
# The single execution path with retry + failover
# ---------------------------------------------------------------------------


def generate_content(
    client: Any,
    *,
    contents: Any,
    config: Any = None,
    models: str | Sequence[str] | None = None,
    operation: str | None = None,
    context: Mapping[str, Any] | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] | None = None,
    validator: Callable[[Any], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> Any:
    """Run one Gemini ``generate_content`` request through the unified policy.

    The request is attempted on the first model up to ``policy.max_attempts``
    times with exponential backoff. Transient failures fail over to the next
    model in the chain; permanent failures are raised immediately, without a
    retry or a failover. When the whole chain is exhausted the *original*
    provider exception is re-raised so the real error (for example a 503 from
    Google) reaches the caller.

    ``validator`` runs on every returned response and may raise to reject it
    (for example an empty structured payload). A retryable rejection is treated
    exactly like a transient provider failure.

    ``policy.total_timeout_seconds`` caps the wall-clock budget of the whole
    walk (0 disables it), and the backoff honours a provider ``Retry-After``
    hint when one is present.
    """
    chain = resolve_model_chain(models)
    policy = retry_policy or RetryPolicy.from_env()
    sleeper = sleep or time.sleep
    now = clock or time.monotonic
    context_fields = dict(context or {})
    deadline = now() + policy.total_timeout_seconds if policy.total_timeout_seconds > 0 else None

    _log_event(
        logging.INFO,
        "GEMINI_CHAIN_CONFIGURED",
        operation=operation,
        models=",".join(chain),
        model_count=len(chain),
        total_timeout_seconds=policy.total_timeout_seconds or None,
        **context_fields,
    )

    last_error: Exception | None = None
    budget_exhausted = False
    for model_index, model in enumerate(chain, start=1):
        for attempt in range(1, policy.max_attempts + 1):
            if deadline is not None and now() >= deadline:
                budget_exhausted = True
                break
            _log_event(
                logging.INFO,
                "GEMINI_ATTEMPT_START",
                operation=operation,
                model=model,
                model_index=model_index,
                attempt=attempt,
                max_attempts=policy.max_attempts,
                **context_fields,
            )
            try:
                response = client.models.generate_content(model=model, contents=contents, config=config)
                if validator is not None:
                    validator(response)
            except Exception as exc:
                code, transient = classify_gemini_error(exc)
                last_error = exc
                if not transient:
                    _log_event(
                        logging.WARNING,
                        "GEMINI_PERMANENT_ERROR",
                        operation=operation,
                        model=model,
                        model_index=model_index,
                        attempt=attempt,
                        code=code,
                        error=str(exc),
                        **context_fields,
                    )
                    raise
                _log_event(
                    logging.WARNING,
                    "GEMINI_TRANSIENT_ERROR",
                    operation=operation,
                    model=model,
                    model_index=model_index,
                    attempt=attempt,
                    code=code,
                    error=str(exc),
                    **context_fields,
                )
                if attempt < policy.max_attempts:
                    delay = policy.delay_for(attempt)
                    hint = retry_after_seconds(exc)
                    if hint is not None:
                        delay = max(delay, hint)
                    if deadline is not None:
                        remaining = deadline - now()
                        if remaining <= 0:
                            budget_exhausted = True
                            break
                        delay = min(delay, remaining)
                    _log_event(
                        logging.WARNING,
                        "GEMINI_RETRY_BACKOFF",
                        operation=operation,
                        model=model,
                        attempt=attempt,
                        delay_seconds=delay,
                        retry_after_seconds=hint,
                        **context_fields,
                    )
                    sleeper(delay)
                    continue
                break
            else:
                _log_event(
                    logging.INFO,
                    "GEMINI_ATTEMPT_SUCCESS",
                    operation=operation,
                    model=model,
                    model_index=model_index,
                    attempt=attempt,
                    **context_fields,
                )
                return response

        if budget_exhausted:
            break

        if model_index < len(chain):
            _log_event(
                logging.WARNING,
                "GEMINI_MODEL_FAILOVER",
                operation=operation,
                from_model=model,
                to_model=chain[model_index],
                model_index=model_index,
                code=classify_gemini_error(last_error)[0] if last_error is not None else None,
                **context_fields,
            )

    if budget_exhausted:
        _log_event(
            logging.WARNING,
            "GEMINI_BUDGET_EXHAUSTED",
            operation=operation,
            total_timeout_seconds=policy.total_timeout_seconds,
            **context_fields,
        )

    if last_error is None:
        raise GeminiOperationError(
            GEMINI_DEADLINE_EXCEEDED,
            "Gemini request budget was exhausted before any attempt ran.",
            True,
        )

    # Every model and every attempt is exhausted: surface the real provider error.
    raise last_error


async def generate_content_async(
    client: Any,
    *,
    contents: Any,
    config: Any = None,
    models: str | Sequence[str] | None = None,
    operation: str | None = None,
    context: Mapping[str, Any] | None = None,
    retry_policy: RetryPolicy | None = None,
    validator: Callable[[Any], None] | None = None,
) -> Any:
    """Async wrapper around :func:`generate_content` without blocking the loop."""
    return await asyncio.to_thread(
        generate_content,
        client,
        contents=contents,
        config=config,
        models=models,
        operation=operation,
        context=context,
        retry_policy=retry_policy,
        validator=validator,
    )