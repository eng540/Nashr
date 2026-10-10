import pytest

from app.infrastructure.artifact_storage import (
    ArtifactStorageConfigurationError,
    S3ArtifactStorage,
)


class FakeS3Client:
    def __init__(self):
        self.put_calls = []
        self.presign_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        self.presign_calls.append((operation, Params, ExpiresIn))
        return "https://storage.example/signed-media"


@pytest.mark.asyncio
async def test_put_stores_private_object_and_returns_stable_uri():
    client = FakeS3Client()
    storage = S3ArtifactStorage(client=client, bucket="nashr-media")

    uri = await storage.put(
        key="artifacts/source-1/job-2/image.png",
        content=b"image-bytes",
        content_type="image/png",
    )

    assert uri == "s3://nashr-media/artifacts/source-1/job-2/image.png"
    assert client.put_calls == [{
        "Bucket": "nashr-media",
        "Key": "artifacts/source-1/job-2/image.png",
        "Body": b"image-bytes",
        "ContentType": "image/png",
    }]


@pytest.mark.asyncio
async def test_presign_get_only_accepts_the_configured_bucket_and_bounded_expiry():
    client = FakeS3Client()
    storage = S3ArtifactStorage(client=client, bucket="nashr-media")

    url = await storage.presign_get(
        "s3://nashr-media/artifacts/source-1/job-2/image.png",
        expires_seconds=300,
    )

    assert url == "https://storage.example/signed-media"
    assert client.presign_calls == [(
        "get_object",
        {"Bucket": "nashr-media", "Key": "artifacts/source-1/job-2/image.png"},
        300,
    )]
    with pytest.raises(ValueError, match="unexpected bucket"):
        await storage.presign_get("s3://another-bucket/artifacts/source-1/image.png")
    with pytest.raises(ValueError, match="between 60 and 900"):
        await storage.presign_get("s3://nashr-media/artifacts/source-1/image.png", expires_seconds=3600)


@pytest.mark.asyncio
async def test_storage_rejects_unsafe_keys_and_uris():
    storage = S3ArtifactStorage(client=FakeS3Client(), bucket="nashr-media")

    with pytest.raises(ValueError, match="unsafe path"):
        await storage.put(key="artifacts/../secret.png", content=b"x", content_type="image/png")
    with pytest.raises(ValueError, match="unsafe path"):
        await storage.presign_get("s3://nashr-media/artifacts/%2e%2e/secret.png")
    with pytest.raises(ValueError, match="valid private s3"):
        await storage.presign_get("https://storage.example/secret.png")


def test_from_environment_fails_closed_when_storage_is_not_configured(monkeypatch):
    for name in (
        "ARTIFACT_STORAGE_ENDPOINT_URL",
        "ARTIFACT_STORAGE_BUCKET",
        "ARTIFACT_STORAGE_ACCESS_KEY_ID",
        "ARTIFACT_STORAGE_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ArtifactStorageConfigurationError, match="not configured"):
        S3ArtifactStorage.from_environment()
