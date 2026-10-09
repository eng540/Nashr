import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.production_jobs import ProductionJobRunner, create_production_job, resume_production_job
from app.domain.production_jobs import ProductionJobItemStatus, ProductionJobStatus, ProductionScope
from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, ProductionJobItemModel, ProductionJobModel, SourceModel, TopicModel
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


class RecordingDrafter:
    def __init__(self, fail_titles: set[str] | None = None):
        self.calls = []
        self.fail_titles = fail_titles or set()

    async def draft(self, *, title: str, content: str, source_name: str, pdf_slice: bytes | None = None, system_prompt: str | None = None) -> str:
        self.calls.append(title)
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
        assert "EOF marker" in (item.error_message or "") or "PDF" in (item.error_message or "")
        assert posts == []
