from urllib.parse import parse_qs, urlsplit

import pytest

from app.infrastructure.storage import S3CompatibleObjectStorage, StorageConfigurationError


class FakeResponse:
    def raise_for_status(self):
        return None


class FakeHTTPClient:
    def __init__(self):
        self.request = None

    async def put(self, url, *, content, headers):
        self.request = {"url": url, "content": content, "headers": headers}
        return FakeResponse()


@pytest.mark.asyncio
async def test_s3_compatible_storage_uploads_signed_bytes_and_returns_uri():
    client = FakeHTTPClient()
    storage = S3CompatibleObjectStorage(
        endpoint_url="https://objects.example.test",
        bucket="test-bucket",
        access_key_id="test-access",
        secret_access_key="test-secret",
        region="us-east-1",
        http_client=client,
    )
    uri = await storage.save("cover.png", b"png-data", prefix="job-123", mime_type="image/png")
    assert uri.startswith("s3://test-bucket/artifacts/job-123/")
    assert client.request["content"] == b"png-data"
    assert client.request["headers"]["content-type"] == "image/png"
    assert client.request["headers"]["authorization"].startswith("AWS4-HMAC-SHA256 Credential=test-access/")
    assert "x-amz-content-sha256" in client.request["headers"]


@pytest.mark.asyncio
async def test_s3_compatible_storage_signs_short_lived_download_urls():
    storage = S3CompatibleObjectStorage(
        endpoint_url="https://objects.example.test",
        bucket="test-bucket",
        access_key_id="test-access",
        secret_access_key="test-secret",
        region="us-east-1",
    )
    url = await storage.download_url("s3://test-bucket/artifacts/job-123/cover.png", expires_seconds=600)
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert params["X-Amz-Expires"] == ["600"]
    assert params["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert len(params["X-Amz-Signature"][0]) == 64


@pytest.mark.asyncio
async def test_s3_compatible_storage_rejects_unknown_bucket_and_invalid_expiry():
    storage = S3CompatibleObjectStorage(
        endpoint_url="https://objects.example.test",
        bucket="test-bucket",
        access_key_id="test-access",
        secret_access_key="test-secret",
        region="us-east-1",
    )
    with pytest.raises(ValueError, match="does not belong"):
        await storage.download_url("s3://other-bucket/path.png")
    with pytest.raises(ValueError, match="expiry"):
        await storage.download_url("s3://test-bucket/path.png", expires_seconds=700000)


def test_s3_compatible_storage_requires_runtime_credentials(monkeypatch):
    for name in (
        "OBJECT_STORAGE_ENDPOINT_URL", "OBJECT_STORAGE_BUCKET",
        "OBJECT_STORAGE_ACCESS_KEY_ID", "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_REGION",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(StorageConfigurationError, match="Durable media storage is not configured"):
        S3CompatibleObjectStorage.from_env()
