from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.artifacts import ensure_post_artifact, persist_generic_artifact
from app.application.recipe_engine import ProduceTextArtifactCapability, ProductionExecutionContext
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.domain.posts import Post, PostStatus
from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, ProductionJobModel, SourceModel
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
async def test_text_capability_populates_required_source_and_title_metadata():
    now = datetime.now(timezone.utc)
    context = contract_context("TEXT", "text/plain", "INLINE", ["source", "title"], 1000)
    async with SessionFactory() as session:
        source_id, unit_id = await _source_unit(session)
        job_id = uuid4()
        session.add(ProductionJobModel(
            id=job_id, source_id=source_id, scope="SOURCE", status="RUNNING", total_items=1,
        ))
        await session.commit()

        class FakeDrafter:
            async def draft(self, **kwargs):
                return "مادة نصية للاختبار"

        capability = ProduceTextArtifactCapability(FakeDrafter())
        execution = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id},
            configuration={"editorial_prompt": {"body": "اكتب نصًا دقيقًا."}},
            run_id=job_id,
            resolved_context=context,
        )
        artifact = await capability.execute(execution)
        assert artifact.metadata["source"] == "generic-artifact.pdf"
        assert artifact.metadata["title"] == "Test source material"


@pytest.mark.asyncio
async def test_post_artifact_populates_required_source_metadata_from_knowledge_unit():
    now = datetime.now(timezone.utc)
    context = contract_context("POST", "text/plain", "INLINE", ["source", "title"], 1000)
    async with SessionFactory() as session:
        source_id, unit_id = await _source_unit(session)
        post_id = uuid4()
        session.add(PostModel(
            id=post_id, knowledge_unit_id=unit_id, content="منشور موثق بالمصدر",
            status=PostStatus.DRAFT.value,
        ))
        await session.commit()
        post = Post(
            id=post_id, knowledge_unit_id=unit_id, content="منشور موثق بالمصدر",
            status=PostStatus.DRAFT, created_at=now, updated_at=now,
            reviewed_at=None, review_note=None,
        )
        context["output_contract"]["key"] = "TEST_POST_SOURCE_CONTRACT"
        saved = await ensure_post_artifact(
            session, post, production_job_id=None, resolved_context=context,
        )
        assert saved.output_contract_key == "TEST_POST_SOURCE_CONTRACT"
        assert saved.output_contract_version == 1
        assert saved.metadata["source"] == "generic-artifact.pdf"
        assert saved.metadata["title"] == "Test source material"


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



@pytest.mark.asyncio
async def test_same_artifact_kind_is_independent_across_explicit_claims():
    now = datetime.now(timezone.utc)
    context = contract_context("TEXT", "text/plain", "INLINE", ["language"], 500)
    async with SessionFactory() as session:
        source_id, unit_id = await _source_unit(session)
        first_job_id, second_job_id = uuid4(), uuid4()
        session.add_all([
            ProductionJobModel(id=first_job_id, source_id=source_id, scope="SOURCE", status="COMPLETED", total_items=1),
            ProductionJobModel(id=second_job_id, source_id=source_id, scope="SOURCE", status="COMPLETED", total_items=1),
        ])
        await session.commit()
        first = await persist_generic_artifact(session, Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.TEXT,
            content="First explicit claim", status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="text/plain",
            production_job_id=first_job_id, metadata={"language": "ar"},
        ), resolved_context=context)
        second = await persist_generic_artifact(session, Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.TEXT,
            content="Second explicit claim", status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="text/plain",
            production_job_id=second_job_id, metadata={"language": "ar"},
        ), resolved_context=context)
        assert first.id != second.id
        assert first.content == "First explicit claim"
        assert second.content == "Second explicit claim"
        assert first.production_job_id != second.production_job_id



@pytest.mark.asyncio
async def test_thematic_text_artifact_keeps_every_source_and_enters_existing_review_queue():
    from app.application.generic_artifact_review import GenericArtifactReviewService
    from app.application.thematic_composition import ThematicCompositionResult, persist_thematic_draft
    from app.domain.editorial import EditorialSourceMaterial

    now = datetime.now(timezone.utc)
    job_id = uuid4()
    context = contract_context("TEXT", "text/plain", "INLINE", ["title", "theme", "sources"], 20000)
    async with SessionFactory() as session:
        source_a, source_b = uuid4(), uuid4()
        unit_a, unit_b = uuid4(), uuid4()
        session.add_all([
            SourceModel(id=source_a, filename="book-a.pdf", book_title="كتاب أ", mime_type="application/pdf", storage_path="./storage/test/book-a.pdf", size_bytes=1, status="STORED"),
            SourceModel(id=source_b, filename="book-b.pdf", book_title="كتاب ب", mime_type="application/pdf", storage_path="./storage/test/book-b.pdf", size_bytes=1, status="STORED"),
            KnowledgeUnitModel(id=unit_a, source_id=source_a, position=1, title="مادة أ", content="النص الأصلي أ"),
            KnowledgeUnitModel(id=unit_b, source_id=source_b, position=1, title="مادة ب", content="النص الأصلي ب"),
            ProductionJobModel(id=job_id, source_id=source_a, scope="SELECTION", status="RUNNING", total_items=1),
        ])
        await session.commit()
        result = ThematicCompositionResult(
            theme="الأمانة في التراث",
            content="تركيب تحريري للمراجعة البشرية",
            sources=(
                EditorialSourceMaterial(str(unit_a), "مادة أ", "النص الأصلي أ", "كتاب أ", "ص 12"),
                EditorialSourceMaterial(str(unit_b), "مادة ب", "النص الأصلي ب", "كتاب ب", None),
            ),
        )
        saved = await persist_thematic_draft(
            session, result, resolved_context=context, production_job_id=job_id
        )
        assert saved.source_knowledge_unit_id == unit_a
        assert saved.metadata["composition_mode"] == "MULTI_SOURCE_THEMATIC"
        assert saved.metadata["language"] == "ar"
        assert saved.metadata["source_knowledge_unit_ids"] == [str(unit_a), str(unit_b)]
        assert [source["source_name"] for source in saved.metadata["sources"]] == ["كتاب أ", "كتاب ب"]
        review_queue = await GenericArtifactReviewService(session).list("DRAFT")
        assert any(item["id"] == str(saved.id) for item in review_queue)
