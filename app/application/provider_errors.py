"""Shared classification for provider requests whose outcome may be ambiguous."""


class ProviderOutcomeUnknownError(RuntimeError):
    """A provider may have accepted work, but Nashr has no durable result/handle."""

    code = "PROVIDER_OUTCOME_UNKNOWN"


def _http_status(exc: Exception) -> int | None:
    for attribute in ("status_code", "http_status", "status", "code"):
        value = getattr(exc, attribute, None)
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            nested = getattr(value, "value", None)
            if isinstance(nested, int):
                return nested
    return None


def is_ambiguous_provider_error(exc: Exception) -> bool:
    """Return true only for failures where acceptance/completion may be unknown."""
    status = _http_status(exc)
    if status is not None:
        if status in {408, 409, 425, 429} or status >= 500:
            return True
        if 400 <= status < 500:
            return False
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return (
        isinstance(exc, (TimeoutError, ConnectionError, OSError))
        or any(token in name for token in ("timeout", "connection", "transport", "network"))
        or any(token in message for token in ("timed out", "timeout", "connection reset", "connection aborted", "network is unreachable"))
    )


def raise_if_provider_outcome_unknown(exc: Exception, *, provider: str) -> None:
    """Raise a normalized non-retry-safe error for an ambiguous provider failure."""
    if isinstance(exc, ProviderOutcomeUnknownError):
        raise exc
    if is_ambiguous_provider_error(exc):
        raise ProviderOutcomeUnknownError(
            f"{provider} may have accepted the request, but Nashr did not capture a durable result. Reconcile before retrying."
        ) from exc
