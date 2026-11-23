import httpx
import pytest

from app.application.media_bank import IngestReadyMedia
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.session import SessionFactory
from app.main import app


class _FakeS3Client:
    def __init__(self):
        self.puts = []
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.puts.append({"Bucket": Bucket, "Key": Key, "ContentType": ContentType})
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        return {"Body": _FakeBody(self.objects[(Bucket, Key)])}


class _FakeBody:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def close(self):
        pass


async def _ingest(storage):
    async with SessionFactory() as session:
        artifact = await IngestReadyMedia(storage=storage).execute(
            session,
            filename="ready-video.mp4",
            content_type="video/mp4",
            data=b"\x00\x00\x00\x18ftypmp42\x00" * 4,
            caption="مقطع جاهز للنشر",
        )
        return artifact.id


@pytest.mark.asyncio
async def test_media_bank_ingest_review_and_telegram_draft(monkeypatch):
    monkeypatch.setenv("TELEGRAM_DESTINATION_ID", "@nashr_media_bank")
    storage = S3ArtifactStorage(client=_FakeS3Client(), bucket="media-bank-test")
    artifact_id = await _ingest(storage)

    assert storage.puts, "Ingest must store the uploaded media bytes."
    assert storage.puts[0]["Key"].startswith("artifacts/media-bank/")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        drafts = await client.get("/api/artifacts?review_status=DRAFT")
        assert drafts.status_code == 200
        draft_row = next((row for row in drafts.json() if row["id"] == str(artifact_id)), None)
        assert draft_row is not None
        assert draft_row["kind"] == "VIDEO"
        assert draft_row["mime_type"] == "video/mp4"
        assert draft_row["storage_uri"].startswith("s3://media-bank-test/artifacts/media-bank/")
        assert draft_row["metadata"]["caption"] == "مقطع جاهز للنشر"

        approve = await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        assert approve.status_code == 200, approve.text

        draft = await client.post(f"/api/artifacts/{artifact_id}/telegram-media-draft")
        assert draft.status_code == 201, draft.text
        body = draft.json()
        assert body["status"] == "DRAFT"
        assert body["platform"] == "telegram"
        assert body["destination"] == "@nashr_media_bank"
        assert body["content"] == "مقطع جاهز للنشر"

        # Draft creation is idempotent per artifact + destination.
        again = await client.post(f"/api/artifacts/{artifact_id}/telegram-media-draft")
        assert again.status_code == 201, again.text
        assert again.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_media_bank_ingest_rejects_unsupported_type():
    storage = S3ArtifactStorage(client=_FakeS3Client(), bucket="media-bank-test")
    async with SessionFactory() as session:
        with pytest.raises(ValueError):
            await IngestReadyMedia(storage=storage).execute(
                session,
                filename="notes.txt",
                content_type="text/plain",
                data=b"plain text",
                caption=None,
            )
    assert not storage.puts
