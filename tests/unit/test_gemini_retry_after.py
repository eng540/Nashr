from types import SimpleNamespace

from app.adapters.gemini_policy import retry_after_seconds


def test_retry_after_seconds_reads_gemini_retry_info_duration() -> None:
    error = SimpleNamespace(
        details=[
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "13.8s",
            }
        ],
        message="RESOURCE_EXHAUSTED",
    )

    assert retry_after_seconds(error) == 13.8


def test_retry_after_seconds_reads_human_readable_quota_message() -> None:
    error = RuntimeError(
        "Quota exceeded. Please retry in 5.3s."
    )

    assert retry_after_seconds(error) == 5.3


def test_retry_after_seconds_prefers_http_retry_after_header() -> None:
    error = SimpleNamespace(
        response=SimpleNamespace(headers={"retry-after": "7"}),
        details={"retryDelay": "13.8s"},
    )

    assert retry_after_seconds(error) == 7.0


def test_retry_after_seconds_returns_none_without_a_provider_hint() -> None:
    assert retry_after_seconds(RuntimeError("temporary error")) is None
