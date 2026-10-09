import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.production_jobs import ProductionJobRunner, create_production_job, resume_production_job
from app.application.control_plane import PromptTemplateService
from app.domain.production_jobs import ProductionJobItemStatus, ProductionJobStatus, ProductionScope
from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, ProductionJobItemModel, ProductionJobModel, SourceModel, TopicModel, PromptTemplateModel, PromptTemplateVersionModel
from app.infrastructure.database.control_plane import PromptTemplateRepository
from app.infrastructure.database.session import SessionFactory


async def _fixture(materials: int = 5, topics: int = 2):
    source_id = uuid4()
    topic_ids = [uuid4() for _ in range(topics)]
    unit_ids = []
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename="production.pdf", mime_type="application/pdf",
            storage_path="./storage/test/production.pdf", size_bytes=10, status="STORED",
        ))
        for position, topic_id in enumerate(topic_ids, start=1):
            session.add(TopicModel(
                id=topic_id, source_id=source_id, position=position,
                title=f"Topic {position}", description=f"Description {position}",
            ))
        for position in range(1, materials + 1):
            unit_id = uuid4()
            unit_ids.append(unit_id)
            topic_id = topic_ids[(position - 1) % topics]
            session.add(KnowledgeUnitModel(
                id=unit_id, source_id=source_id, topic_id=topic_id, position=position,
                title=f"Material {position}", content=f"Content {position}",
            ))
        await session.commit()
    return source_id, topic_ids, unit_ids


async def _reset_editorial_prompt(session, body: str):
    """Restore the migration-seeded canonical prompt for order-independent tests."""
    template = (await session.execute(
        select(PromptTemplateModel).where(PromptTemplateModel.key == "editorial.drafter")
    )).scalar_one()
    versions = (await session.execute(
        select(PromptTemplateVersionModel).where(
            PromptTemplateVersionModel.prompt_template_id == template.id
        )
    )).scalars().all()
    for version in versions:
        if version.version != 1:
            await session.delete(version)
    await session.flush()
    version_one = next(version for version in versions if version.version == 1)
    version_one.body = body
    version_one.status = "PUBLISHED"
    await session.flush()
    return template


class RecordingDrafter:
    def __init__(self, fail_titles: set[str] | None = None):
        self.calls = []
        self.prompts = []
        self.fail_titles = fail_titles or set()

    async def draft(self, *, title: str, content: str, source_name: str, pdf_slice: bytes | None = None, system_prompt: str | None = None) -> str:
        self.calls.append(title)
        self.prompts.append(system_prompt)
        if title in self.fail_titles:
            raise RuntimeError(f"failed: {title}")
        return f"POST::{title}"


async def test_source_scope_snapshots_all_materials_in_deterministic_order():
    source_id, _, unit_ids = await _fixture()
    async with SessionFactory() as session:
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
        items = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        assert job.total_items == 5
        assert [item.knowledge_unit_id for item in items] == unit_ids


async def test_topic_scope_only_snapshots_topic_materials():
    source_id, topic_ids, unit_ids = await _fixture()
    async with SessionFactory() as session:
        job = await create_production_job(session, source_id, ProductionScope.TOPIC, topic_id=topic_ids[1])
        items = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        assert [item.knowledge_unit_id for item in items] == [unit_ids[1], unit_ids[3]]


async def test_explicit_selection_snapshots_only_requested_materials():
    source_id, _, unit_ids = await _fixture()
    async with SessionFactory() as session:
        job = await create_production_job(session, source_id, ProductionScope.SELECTION, knowledge_unit_ids=[unit_ids[4], unit_ids[1]])
        items = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        assert [item.knowledge_unit_id for item in items] == [unit_ids[1], unit_ids[4]]


async def test_published_prompt_change_does_not_mutate_existing_job_context():
    source_id, _, _ = await _fixture(materials=2)
    async with SessionFactory() as session:
        await _reset_editorial_prompt(session, "prompt-v1")
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
        original_context = job.resolved_context.copy()
        service = PromptTemplateService(session)
        draft = await service.create_draft("editorial.drafter", "prompt-v2")
        await service.publish("editorial.drafter", draft.version)
        await session.refresh(job)
        assert job.resolved_context == original_context

    drafter = RecordingDrafter()
    await ProductionJobRunner(drafter).run(job.id)
    assert drafter.prompts == ["prompt-v1", "prompt-v1"]


async def test_legacy_pinned_job_without_context_keeps_its_existing_prompt():
    source_id, _, _ = await _fixture(materials=1)
    async with SessionFactory() as session:
        await _reset_editorial_prompt(session, "legacy-pinned-prompt")
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
        job.resolved_context = None
        await session.commit()

    drafter = RecordingDrafter()
    await ProductionJobRunner(drafter).run(job.id)
    assert drafter.prompts == ["legacy-pinned-prompt"]


async def test_single_job_produces_posts_and_completes():
    source_id, _, unit_ids = await _fixture(materials=3)
    async with SessionFactory() as session:
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
    await ProductionJobRunner(RecordingDrafter()).run(job.id)
    async with SessionFactory() as session:
        final = (await session.execute(select(ProductionJobModel).where(ProductionJobModel.id == job.id))).scalar_one()
        items = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        posts = (await session.execute(select(PostModel).where(PostModel.knowledge_unit_id.in_(unit_ids)))).scalars().all()
        assert final.status == ProductionJobStatus.COMPLETED.value
        assert final.started_at is not None
        assert final.completed_at is not None
        assert final.updated_at is not None
        assert final.completed_items == 3
        assert final.failed_items == 0
        assert [item.status for item in items] == [ProductionJobItemStatus.COMPLETED.value] * 3
        assert len(posts) == 3
        assert all(item.post_id is not None for item in items)


async def test_failure_is_isolated_and_later_items_continue():
    source_id, _, _ = await _fixture(materials=4)
    async with SessionFactory() as session:
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
    await ProductionJobRunner(RecordingDrafter({"Material 2"})).run(job.id)
    async with SessionFactory() as session:
        final = (await session.execute(select(ProductionJobModel).where(ProductionJobModel.id == job.id))).scalar_one()
        items = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        assert final.status == ProductionJobStatus.FAILED.value
        assert final.started_at is not None
        assert final.completed_at is not None
        assert final.updated_at is not None
        assert final.error_code == "PRODUCTION_ITEMS_FAILED"
        assert final.completed_items == 3
        assert final.failed_items == 1
        assert [item.status for item in items] == ["COMPLETED", "FAILED", "COMPLETED", "COMPLETED"]


async def test_existing_post_is_reused_by_job():
    source_id, _, unit_ids = await _fixture(materials=1)
    async with SessionFactory() as session:
        existing = PostModel(id=uuid4(), knowledge_unit_id=unit_ids[0], content="Existing", status="DRAFT")
        session.add(existing)
        await session.commit()
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
    await ProductionJobRunner(RecordingDrafter()).run(job.id)
    async with SessionFactory() as session:
        posts = (await session.execute(select(PostModel).where(PostModel.knowledge_unit_id == unit_ids[0]))).scalars().all()
        item = (await session.execute(select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id))).scalar_one()
        assert len(posts) == 1
        assert posts[0].id == existing.id
        assert item.post_id == existing.id


async def test_resume_skips_completed_and_retries_failed_only_when_requested():
    source_id, _, unit_ids = await _fixture(materials=3)
    async with SessionFactory() as session:
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
        items = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        existing_post = PostModel(
            id=uuid4(),
            knowledge_unit_id=unit_ids[0],
            content="Already completed",
            status="DRAFT",
        )
        session.add(existing_post)
        await session.flush()
        items[0].status = "COMPLETED"
        items[0].post_id = existing_post.id
        items[1].status = "FAILED"
        items[1].error_code = "TEST"
        items[1].error_message = "failure"
        job.status = "FAILED"
        job.completed_items = 1
        job.failed_items = 1
        await session.commit()
        resumed = await resume_production_job(session, job.id, retry_failed=False)
        assert resumed.status == "QUEUED"
        states = (await session.execute(
            select(ProductionJobItemModel.status).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        assert states == ["COMPLETED", "FAILED", "PENDING"]
    await ProductionJobRunner(RecordingDrafter()).run(job.id)
    async with SessionFactory() as session:
        final = (await session.execute(select(ProductionJobModel).where(ProductionJobModel.id == job.id))).scalar_one()
        assert final.status == ProductionJobStatus.FAILED.value
        resumed = await resume_production_job(session, job.id, retry_failed=True)
        assert resumed.status == "QUEUED"
    await ProductionJobRunner(RecordingDrafter()).run(job.id)
    async with SessionFactory() as session:
        final = (await session.execute(select(ProductionJobModel).where(ProductionJobModel.id == job.id))).scalar_one()
        items = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
        )).scalars().all()
        posts = (await session.execute(select(PostModel).where(PostModel.knowledge_unit_id.in_(unit_ids)))).scalars().all()
        assert final.status == ProductionJobStatus.COMPLETED.value
        assert len(posts) == 3
        assert [item.status for item in items] == ["COMPLETED"] * 3


async def test_duplicate_selection_is_rejected():
    source_id, _, unit_ids = await _fixture(materials=2)
    async with SessionFactory() as session:
        with pytest.raises(ValueError, match="duplicates"):
            await create_production_job(session, source_id, ProductionScope.SELECTION, knowledge_unit_ids=[unit_ids[0], unit_ids[0]])


async def test_concurrent_job_execution_claims_job_once():
    source_id, _, unit_ids = await _fixture(materials=5)
    async with SessionFactory() as session:
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)

    runner_a = ProductionJobRunner(RecordingDrafter())
    runner_b = ProductionJobRunner(RecordingDrafter())
    await asyncio.gather(runner_a.run(job.id), runner_b.run(job.id))

    async with SessionFactory() as session:
        final = (await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == job.id)
        )).scalar_one()
        items = (await session.execute(
            select(ProductionJobItemModel)
            .where(ProductionJobItemModel.job_id == job.id)
            .order_by(ProductionJobItemModel.position)
        )).scalars().all()
        posts = (await session.execute(
            select(PostModel).where(PostModel.knowledge_unit_id.in_(unit_ids))
        )).scalars().all()
        assert final.status == ProductionJobStatus.COMPLETED.value
        assert final.completed_items == 5
        assert len(posts) == 5
        assert [item.status for item in items] == ["COMPLETED"] * 5


async def test_invalid_source_pdf_fails_job_instead_of_using_text_fallback(tmp_path):
    source_id, _, unit_ids = await _fixture(materials=1)
    invalid_pdf = tmp_path / "invalid.pdf"
    invalid_pdf.write_bytes(b"this is not a PDF")

    async with SessionFactory() as session:
        source = (await session.execute(
            select(SourceModel).where(SourceModel.id == source_id)
        )).scalar_one()
        unit = (await session.execute(
            select(KnowledgeUnitModel).where(KnowledgeUnitModel.id == unit_ids[0])
        )).scalar_one()
        source.storage_path = str(invalid_pdf)
        unit.discovery_page_start = 1
        unit.discovery_page_end = 1
        await session.commit()
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)

    await ProductionJobRunner(RecordingDrafter()).run(job.id)

    async with SessionFactory() as session:
        final = (await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == job.id)
        )).scalar_one()
        item = (await session.execute(
            select(ProductionJobItemModel).where(
                ProductionJobItemModel.job_id == job.id
            )
        )).scalar_one()
        posts = (await session.execute(
            select(PostModel).where(PostModel.knowledge_unit_id == unit_ids[0])
        )).scalars().all()
        assert final.status == ProductionJobStatus.FAILED.value
        assert final.failed_items == 1
        assert final.completed_at is not None
        assert item.status == ProductionJobItemStatus.FAILED.value
        assert item.error_code == "PRODUCTION_ERROR"
        assert any(marker in (item.error_message or "") for marker in ("EOF marker", "PDF", "Stream has ended unexpectedly"))
        assert posts == []


async def test_production_job_pins_prompt_across_publish_retry_and_new_job():
    source_id, _, unit_ids = await _fixture(materials=4, topics=1)
    async with SessionFactory() as session:
        template = await _reset_editorial_prompt(session, "prompt-v1")
        await session.commit()

        old_job = await create_production_job(
            session, source_id, ProductionScope.SELECTION,
            knowledge_unit_ids=unit_ids[:3],
        )
        assert old_job.editorial_prompt_key == "editorial.drafter"
        assert old_job.editorial_prompt_version == 1
        assert old_job.editorial_prompt_body == "prompt-v1"

        session.add(PromptTemplateVersionModel(
            id=uuid4(), prompt_template_id=template.id, version=2,
            body="draft-v2-must-not-run", status="DRAFT",
        ))
        await session.commit()
        # A draft does not affect the currently published production prompt.
        draft_job = await create_production_job(
            session, source_id, ProductionScope.SELECTION,
            knowledge_unit_ids=[unit_ids[3]],
        )
        assert draft_job.editorial_prompt_version == 1
        await PromptTemplateRepository(session).publish("editorial.drafter", 2)
        await session.commit()

        new_job = await create_production_job(
            session, source_id, ProductionScope.SELECTION,
            knowledge_unit_ids=[unit_ids[3]],
        )
        assert new_job.editorial_prompt_version == 2
        assert new_job.editorial_prompt_body == "draft-v2-must-not-run"

    drafter = RecordingDrafter(fail_titles={"Material 2"})
    await ProductionJobRunner(drafter).run(old_job.id)
    assert drafter.prompts == ["prompt-v1", "prompt-v1", "prompt-v1"]

    # Retry the failed item after v2 is published. The old job must still use v1.
    async with SessionFactory() as session:
        await resume_production_job(session, old_job.id, retry_failed=True)
    retry_drafter = RecordingDrafter()
    await ProductionJobRunner(retry_drafter).run(old_job.id)
    assert retry_drafter.prompts == ["prompt-v1"]
    async with SessionFactory() as session:
        pinned = (await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == old_job.id)
        )).scalar_one()
        assert pinned.editorial_prompt_version == 1
        assert pinned.editorial_prompt_body == "prompt-v1"

    new_drafter = RecordingDrafter()
    await ProductionJobRunner(new_drafter).run(new_job.id)
    assert new_drafter.prompts == ["draft-v2-must-not-run"]


async def test_missing_published_editorial_prompt_blocks_job_creation():
    source_id, _, _ = await _fixture(materials=1, topics=1)
    async with SessionFactory() as session:
        template = await _reset_editorial_prompt(session, "prompt-to-archive")
        published = (await session.execute(
            select(PromptTemplateVersionModel).where(
                PromptTemplateVersionModel.prompt_template_id == template.id,
                PromptTemplateVersionModel.status == "PUBLISHED",
            )
        )).scalar_one()
        published.status = "ARCHIVED"
        await session.commit()
        with pytest.raises(LookupError, match="No unique active published prompt"):
            await create_production_job(session, source_id, ProductionScope.SOURCE)


async def test_legacy_job_without_prompt_provenance_fails_without_active_fallback():
    source_id, _, _ = await _fixture(materials=1, topics=1)
    async with SessionFactory() as session:
        await _reset_editorial_prompt(session, "currently-published")
        await session.commit()
        job = await create_production_job(session, source_id, ProductionScope.SOURCE)
        job.editorial_prompt_key = None
        job.editorial_prompt_version = None
        job.editorial_prompt_body = None
        await session.commit()

    drafter = RecordingDrafter()
    await ProductionJobRunner(drafter).run(job.id)
    assert drafter.prompts == []
    async with SessionFactory() as session:
        failed = (await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == job.id)
        )).scalar_one()
        assert failed.status == ProductionJobStatus.FAILED.value
        assert failed.error_code == "PRODUCTION_PROMPT_UNPINNED"
