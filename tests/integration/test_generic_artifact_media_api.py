from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from app.application.artifacts import persist_generic_artifact
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import SessionFactory
from app.main import app


class FakeMediaStorage:
    def __init__(self):
        self.calls = []

    async def presign_get(self, storage_uri: str, *, expires_seconds: int = 300) -> str:
        self.calls.append((storage_uri, expires_seconds))
        return "https://storage.example/signed-image"


async def _create_image_artifact():
    now = datetime.now(timezone.utc)
    source_id, unit_id, artifact_id = uuid4(), uuid4(), uuid4()
    context = {
        "output_contract": {
            "contract_id": str(uuid4()),
            "version_id": str(uuid4()),
            "key": "TEST_IMAGE_ARTIFACT",
            "version": 1,
            "definition": {
                "artifact_kind": "IMAGE",
                "mime_type": "image/png",
                "content_mode": "STORAGE_URI",
                "required_metadata_fields": ["title"],
                "max_content_chars": None,
            },
        }
    }
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename=f"{source_id}.pdf", mime_type="application/pdf",
            storage_path=f"./storage/test/{source_id}.pdf", size_bytes=1, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1,
            title="Media source", content="A source for a media artifact.",
        ))
        await session.commit()
        artifact = Artifact(
            id=artifact_id,
            source_knowledge_unit_id=unit_id,
            kind=ArtifactKind.IMAGE,
            content=None,
            storage_uri="s3://nashr-media/artifacts/test/image.png",
            mime_type="image/png",
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            metadata={"title": "Test image"},
        )
        await persist_generic_artifact(session, artifact, resolved_context=context)
    return artifact_id, context


@pytest.mark.asyncio
async def test_media_url_endpoint_returns_short_lived_signed_url(monkeypatch: pytest.MonkeyPatch):
    artifact_id, _ = await _create_image_artifact()
    storage = FakeMediaStorage()
    monkeypatch.setattr(
        "app.api.artifacts.S3ArtifactStorage.from_environment",
        classmethod(lambda cls: storage),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/artifacts/{artifact_id}/media-url")

    assert response.status_code == 200, response.text
    assert response.json() == {"url": "https://storage.example/signed-image", "expires_in": 300}
    assert storage.calls == [("s3://nashr-media/artifacts/test/image.png", 300)]


@pytest.mark.asyncio
async def test_media_url_endpoint_rejects_inline_text_artifacts():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/artifacts/00000000-0000-0000-0000-000000000001/media-url")
    assert response.status_code == 404
