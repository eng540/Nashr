from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.media_bank import IngestReadyMedia
from app.application.video_library_metadata import restore_video_metadata
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.models import ArtifactModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_media_bank_ingest import _FakeS3Client


@pytest.mark.asyncio
async def test_restore_keeps_media_review_and_caption(monkeypatch):
    storage = S3ArtifactStorage(client=_FakeS3Client(), bucket="restore-test")
    monkeypatch.setattr(S3ArtifactStorage, "from_environment", lambda: storage)
    async with SessionFactory() as session:
        artifact = await IngestReadyMedia().execute(session, filename="42-episode.mp4",
            content_type="video/mp4", data=b"\x00\x00\x00\x18ftypisom" + b"0" * 40, caption="Existing publish caption")
        entry = {"artifact_id": str(artifact.id), "filename": "episode.mp4", "title": "Episode",
            "source_file": "original.txt", "source_original": "Full source" * 200,
            "tiktok_text": "Platform description", "telegram_caption": "Separate short caption",
            "catalog_caption_original": "Original caption", "editorial_notes": ["Internal source note"], "review_notes": ["Engineering review needed"]}
        result = await restore_video_metadata(session, [entry])
        assert result["updated"] == [str(artifact.id)]
        assert (await restore_video_metadata(session, [entry]))["skipped"] == [str(artifact.id)]
        row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == artifact.id))).scalar_one()
        assert row.review_status == "DRAFT"
        assert row.artifact_metadata["caption"] == "Existing publish caption"
        assert row.artifact_metadata["video_library"]["source_original"] == entry["source_original"]
        assert row.storage_uri == artifact.storage_uri
        assert row.artifact_metadata["video_library"]["review_notes"] == entry["review_notes"]
        without_curated = {k: v for k, v in entry.items() if k != "review_notes"}
        assert (await restore_video_metadata(session, [without_curated]))["skipped"] == [str(artifact.id)]
        bad = dict(entry, artifact_id=str(uuid4()))
        with pytest.raises(ValueError, match="missing"):
            await restore_video_metadata(session, [bad])
        await session.rollback()
        bad = dict(entry, filename="different.mp4")
        with pytest.raises(ValueError, match="match"):
            await restore_video_metadata(session, [bad])
        await session.rollback()


@pytest.mark.asyncio
async def test_restore_endpoint_requires_auth_and_rejects_invalid(monkeypatch):
    import httpx
    from app.api.auth import issue_token, SESSION_COOKIE
    from app.main import app
    monkeypatch.setenv("NASHR_AUTH_PASSWORD", "unit-test-only")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        r = await client.post("/api/library/video-metadata", files={"file": ("metadata.json", b"[]")})
        assert r.status_code == 401
        client.cookies.set(SESSION_COOKIE, issue_token("admin"))
        for data in (b"[]", b"{}", b"not json", b"[{}]"):
            r = await client.post("/api/library/video-metadata", files={"file": ("metadata.json", data)})
            assert r.status_code == 422
