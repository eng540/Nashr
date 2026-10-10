from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from app.application.artifacts import persist_generic_artifact
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.main import app
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import SessionFactory


def _context():
    return {
        "output_contract": {
            "contract_id": str(uuid4()), "version_id": str(uuid4()),
            "key": "TEXT_REVIEW_CONTRACT", "version": 1,
            "definition": {
                "artifact_kind": "TEXT", "mime_type": "text/plain", "content_mode": "INLINE",
                "required_metadata_fields": ["language"], "max_content_chars": 500,
            },
        },
        "policy": {
            "policy_id": str(uuid4()), "version_id": str(uuid4()),
            "key": "TEXT_REVIEW_POLICY", "version": 1,
            "definition": {
                "min_content_chars": 1, "max_content_chars": 500,
                "required_terms": ["source"], "forbidden_terms": ["fabricated"], "allow_urls": False,
            },
        },
    }


async def _create_text_artifact(content: str):
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        source_id, unit_id = uuid4(), uuid4()
        session.add(SourceModel(
            id=source_id, filename=f"{uuid4()}.pdf", mime_type="application/pdf",
            storage_path="./storage/test/review-artifact.pdf", size_bytes=1, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1, title="Review source",
            content="A source unit for generic artifact review.",
        ))
        await session.commit()
        artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.TEXT,
            content=content, status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="text/plain", metadata={"language": "en"},
        )
        saved = await persist_generic_artifact(session, artifact, resolved_context=_context())
        return saved.id


@pytest.mark.asyncio
async def test_generic_artifact_review_validates_edits_and_supports_approve_reject():
    approved_id = await _create_text_artifact("source-grounded draft")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        drafts = await client.get("/api/artifacts?review_status=DRAFT")
        assert drafts.status_code == 200
        assert any(row["id"] == str(approved_id) for row in drafts.json())

        invalid = await client.patch(f"/api/artifacts/{approved_id}", json={"content": "fabricated source"})
        assert invalid.status_code == 409
        revised = await client.patch(f"/api/artifacts/{approved_id}", json={"content": "revised source-grounded text"})
        assert revised.status_code == 200, revised.text
        assert revised.json()["content"] == "revised source-grounded text"

        approved = await client.post(f"/api/artifacts/{approved_id}/approve", json={"review_note": "Reviewed"})
        assert approved.status_code == 200, approved.text
        assert approved.json()["review_status"] == "APPROVED"
        repeated = await client.post(f"/api/artifacts/{approved_id}/approve", json={})
        assert repeated.status_code == 409

        rejected_id = await _create_text_artifact("another source-grounded draft")
        rejected = await client.post(f"/api/artifacts/{rejected_id}/reject", json={"review_note": "Needs revision"})
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["review_status"] == "REJECTED"
        assert rejected.json()["review_note"] == "Needs revision"


@pytest.mark.asyncio
async def test_generic_artifact_review_never_treats_post_as_generic_artifact():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/artifacts/00000000-0000-0000-0000-000000000001")
        assert response.status_code == 404
