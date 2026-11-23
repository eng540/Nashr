import httpx
import pytest

from app.application.platform_variants import DerivePlatformVariant, PLATFORM_PROFILES
from app.application.artifacts import persist_generic_artifact
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import SessionFactory
from app.main import app
from datetime import datetime, timezone
from uuid import uuid4


def _test_contract(max_chars=None):
    return {
        "output_contract": {
            "contract_id": str(uuid4()),
            "version_id": str(uuid4()),
            "key": "TEST_TEXT_SOURCE",
            "version": 1,
            "definition": {
                "artifact_kind": "TEXT",
                "mime_type": "text/plain",
                "content_mode": "INLINE",
                "required_metadata_fields": ["source_type"],
                "max_content_chars": max_chars,
            },
        }
    }


async def _seed_text_artifact(content: str) -> str:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        source_id, unit_id = uuid4(), uuid4()
        session.add(SourceModel(
            id=source_id, filename="variant-source.txt", mime_type="text/plain",
            storage_path="s3://test/variant-source.txt", size_bytes=len(content.encode()),
            status="STORED", content_sha256="a" * 64,
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1, title="مادة اختبار النسخ",
            kind="TEXT", content=content[:500], source_reference="variant-source.txt",
        ))
        artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.TEXT,
            content=content, status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="text/plain",
            metadata={"source_type": "TEST_SEED"},
        )
        saved = await persist_generic_artifact(session, artifact, resolved_context=_test_contract())
        await session.commit()
        return str(saved.id)


LONG_ARABIC = "هذا نص عربي طويل مخصص لاختبار اشتقاق نسخ المنصات من المخرجات المعتمدة. " * 8  # ~640 chars


@pytest.mark.asyncio
async def test_platform_variant_requires_approved_source():
    artifact_id = await _seed_text_artifact("نص قصير غير معتمد بعد")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_x_variant_trims_weighted_and_refreshes_idempotently():
    artifact_id = await _seed_text_artifact(LONG_ARABIC)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        approve = await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        assert approve.status_code == 200, approve.text

        first = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["review_status"] == "DRAFT"
        assert body["metadata"]["platform"] == "x"
        assert body["metadata"]["source_artifact_id"] == artifact_id
        assert body["metadata"]["constraints"]["trimmed"] is True
        measure = PLATFORM_PROFILES["x"]["measure"]
        assert measure(body["content"]) <= PLATFORM_PROFILES["x"]["max_text"]
        assert body["output_contract_key"] == "PLATFORM_VARIANT_X"

        second = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert second.status_code == 201, second.text
        assert second.json()["id"] == body["id"], "Re-derivation must refresh the existing DRAFT variant."


@pytest.mark.asyncio
async def test_tiktok_variant_keeps_text_under_utf16_limit_without_trimming_short_text():
    artifact_id = await _seed_text_artifact(LONG_ARABIC)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        resp = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "tiktok"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["content"] == LONG_ARABIC, "Text within the TikTok limit must not be trimmed."
        assert body["metadata"]["constraints"]["trimmed"] is False
        assert body["metadata"]["constraints"]["measure"] == "utf16_units"


@pytest.mark.asyncio
async def test_unknown_platform_rejected():
    artifact_id = await _seed_text_artifact("نص")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        resp = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "snapchat"})
        assert resp.status_code == 422
