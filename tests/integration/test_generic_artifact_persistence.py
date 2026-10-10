from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.artifacts import persist_generic_artifact
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import KnowledgeUnitModel, ProductionJobModel, SourceModel
from app.infrastructure.database.session import SessionFactory


def contract_context(kind: str, mime_type: str, content_mode: str, required: list[str], maximum: int | None) -> dict:
    return {
        "output_contract": {
            "contract_id": str(uuid4()),
            "version_id": str(uuid4()),
            "key": f"TEST_{kind}_CONTRACT",
            "version": 1,
            "definition": {
                "artifact_kind": kind,
                "mime_type": mime_type,
                "content_mode": content_mode,
                "required_metadata_fields": required,
                "max_content_chars": maximum,
            },
        }
    }


async def _source_unit(session):
    source_id = uuid4()
    unit_id = uuid4()
    session.add(SourceModel(
        id=source_id, filename="generic-artifact.pdf", mime_type="application/pdf",
        storage_path="./storage/test/generic-artifact.pdf", size_bytes=1, status="STORED",
    ))
    session.add(KnowledgeUnitModel(
        id=unit_id, source_id=source_id, position=1, title="Test source material",
        content="Source material used to validate provider-neutral artifact persistence.",
    ))
    await session.commit()
    return source_id, unit_id


@pytest.mark.asyncio
async def test_generic_text_artifact_persists_contract_provenance_and_is_idempotent_per_job():
    now = datetime.now(timezone.utc)
    context = contract_context("TEXT", "text/plain", "INLINE", ["language"], 500)
    async with SessionFactory() as session:
        source_id, unit_id = await _source_unit(session)
        job_id = uuid4()
        session.add(ProductionJobModel(
            id=job_id, source_id=source_id, scope="SOURCE", status="QUEUED", total_items=1,
        ))
        await session.commit()
        artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.TEXT,
            content="مادة نصية موثقة", status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="text/plain",
            production_job_id=job_id, metadata={"language": "ar"},
        )
        saved = await persist_generic_artifact(session, artifact, resolved_context=context)
        assert saved.id == artifact.id
        assert saved.kind == ArtifactKind.TEXT
        assert saved.post_id is None
        assert saved.content == "مادة نصية موثقة"
        assert saved.output_contract_key == "TEST_TEXT_CONTRACT"
        assert saved.output_contract_version == 1
        assert saved.metadata == {"language": "ar"}

        retry_artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.TEXT,
            content="different retry content", status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="text/plain",
            production_job_id=job_id, metadata={"language": "ar"},
        )
        reused = await persist_generic_artifact(session, retry_artifact, resolved_context=context)
        assert reused.id == saved.id
        assert reused.content == saved.content


@pytest.mark.asyncio
async def test_generic_image_artifact_persists_storage_reference_and_required_metadata():
    now = datetime.now(timezone.utc)
    context = contract_context("IMAGE", "image/png", "STORAGE_URI", ["alt_text"], None)
    async with SessionFactory() as session:
        _, unit_id = await _source_unit(session)
        artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.IMAGE,
            content=None, storage_uri="s3://nashr-test/artifacts/cover.png",
            status=ArtifactStatus.AVAILABLE.value, created_at=now, updated_at=now,
            mime_type="image/png", metadata={"alt_text": "غلاف توضيحي"},
        )
        saved = await persist_generic_artifact(session, artifact, resolved_context=context)
        assert saved.kind == ArtifactKind.IMAGE
        assert saved.content is None
        assert saved.storage_uri == "s3://nashr-test/artifacts/cover.png"
        assert saved.mime_type == "image/png"
        assert saved.metadata == {"alt_text": "غلاف توضيحي"}


@pytest.mark.asyncio
async def test_generic_artifact_rejects_contract_mismatch_before_persistence():
    now = datetime.now(timezone.utc)
    context = contract_context("IMAGE", "image/png", "STORAGE_URI", [], None)
    artifact = Artifact(
        id=uuid4(), source_knowledge_unit_id=uuid4(), kind=ArtifactKind.TEXT,
        content="This is text", status=ArtifactStatus.AVAILABLE.value,
        created_at=now, updated_at=now, mime_type="text/plain",
    )
    with pytest.raises(ValueError, match="does not match"):
        await persist_generic_artifact(None, artifact, resolved_context=context)
