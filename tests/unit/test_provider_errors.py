import pytest

from app.application.provider_errors import (
    ProviderOutcomeUnknownError,
    is_ambiguous_provider_error,
    raise_if_provider_outcome_unknown,
)


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("request timed out"),
        ConnectionError("connection reset"),
        type("ServerFailure", (RuntimeError,), {"status_code": 503})("server error"),
        type("RateLimited", (RuntimeError,), {"status_code": 429})("rate limited"),
    ],
)
def test_provider_errors_with_ambiguous_outcome_are_not_safe_to_retry(error):
    assert is_ambiguous_provider_error(error)
    with pytest.raises(ProviderOutcomeUnknownError) as caught:
        raise_if_provider_outcome_unknown(error, provider="test provider")
    assert caught.value.code == "PROVIDER_OUTCOME_UNKNOWN"
    assert "Reconcile before retrying" in str(caught.value)


@pytest.mark.parametrize(
    "error",
    [
        type("BadRequest", (RuntimeError,), {"status_code": 400})("invalid request"),
        type("Unauthorized", (RuntimeError,), {"status_code": 401})("unauthorized"),
        RuntimeError("invalid argument in configuration"),
    ],
)
def test_known_provider_rejections_are_not_reclassified_as_unknown(error):
    assert not is_ambiguous_provider_error(error)
    with pytest.raises(RuntimeError):
        raise_if_provider_outcome_unknown(error, provider="test provider")
