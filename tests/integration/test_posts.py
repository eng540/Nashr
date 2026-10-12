from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.adapters.drafting.fake import FakeEditorialDrafter
from app.application.posts import ProducePost
from app.application.reviews import ReviewPost
from app.application.control_plane import ControlPlaneResolver, PromptTemplateService
from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, ProductionJobModel, PublicationModel, ScheduleItemModel, ScheduleModel, SourceModel, TopicModel
from app.infrastructure.database.session import SessionFactory


async def _unit(*, with_topic: bool = True):
    source_id, unit_id = uuid4(), uuid4()
    topic_id = uuid4()
    async with SessionFactory() as session:
        session.add(
            SourceModel(
                id=source_id,
                filename="book.pdf",
                mime_type="application/pdf",
                storage_path="./storage/test/book.pdf",
                size_bytes=10,
                status="STORED",
            )
        )
        if with_topic:
            session.add(
                TopicModel(
                    id=topic_id,
                    source_id=source_id,
                    position=1,
                    title="Topic",
                    description="Description",
                )
            )
        session.add(
            KnowledgeUnitModel(
                id=unit_id,
                source_id=source_id,
                topic_id=topic_id if with_topic else None,
                position=1,
                title="Material title",
                content="Material content",
            )
        )
        await session.commit()
    return source_id, topic_id, unit_id


async def test_produce_single_post() -> None:
    _, _, unit_id = await _unit()
    async with SessionFactory() as session:
        post = await ProducePost(FakeEditorialDrafter()).execute(session, unit_id)
        assert post.knowledge_unit_id == unit_id
        assert post.status.value == "DRAFT"
        assert post.content


async def test_post_provenance_reaches_source_and_topic() -> None:
    source_id, topic_id, unit_id = await _unit()
    async with SessionFactory() as session:
        post = await ProducePost(FakeEditorialDrafter()).execute(session, unit_id)
        row = (
            await session.execute(
                select(PostModel)
                .options(
                    selectinload(PostModel.knowledge_unit)
                    .selectinload(KnowledgeUnitModel.topic)
                    .selectinload(TopicModel.source)
                )
                .where(PostModel.id == post.id)
            )
        ).scalar_one()
        assert row.knowledge_unit.id == unit_id
        assert row.knowledge_unit.topic.id == topic_id
        assert row.knowledge_unit.topic.source.id == source_id


async def test_new_explicit_post_claim_creates_independent_post() -> None:
    _, _, unit_id = await _unit()
    async with SessionFactory() as session:
        drafter = FakeEditorialDrafter()
        first = await ProducePost(drafter).execute(session, unit_id)
        second = await ProducePost(drafter).execute(session, unit_id)
        count = (
            await session.execute(
                select(PostModel).where(PostModel.knowledge_unit_id == unit_id)
            )
        ).scalars().all()
        assert first.id != second.id
        assert len(count) == 2


async def test_retry_within_same_production_job_reuses_its_post() -> None:
    source_id, _, unit_id = await _unit()
    job_id = uuid4()
    async with SessionFactory() as session:
        session.add(ProductionJobModel(id=job_id, source_id=source_id, scope="SELECTION", status="QUEUED", total_items=1))
        await session.commit()
        drafter = FakeEditorialDrafter()
        first = await ProducePost(drafter).execute(session, unit_id, production_job_id=job_id)
        second = await ProducePost(drafter).execute(session, unit_id, production_job_id=job_id)
        count = (
            await session.execute(
                select(PostModel).where(PostModel.production_job_id == job_id)
            )
        ).scalars().all()
        assert first.id == second.id
        assert len(count) == 1


async def test_missing_material_is_rejected() -> None:
    async with SessionFactory() as session:
        with pytest.raises(ValueError, match="Knowledge unit not found"):
            await ProducePost(FakeEditorialDrafter()).execute(session, uuid4())


class FailingDrafter:
    async def draft(self, *, title: str, content: str, source_name: str, pdf_slice: bytes | None = None, system_prompt: str | None = None) -> str:
        raise RuntimeError("draft generation failed")


async def test_draft_failure_leaves_no_post() -> None:
    _, _, unit_id = await _unit()
    async with SessionFactory() as session:
        with pytest.raises(RuntimeError, match="draft generation failed"):
            await ProducePost(FailingDrafter()).execute(session, unit_id)
        rows = (
            await session.execute(
                select(PostModel).where(PostModel.knowledge_unit_id == unit_id)
            )
        ).scalars().all()
        assert rows == []


async def test_new_claim_does_not_reuse_legacy_post() -> None:
    _, _, unit_id = await _unit()
    async with SessionFactory() as session:
        row = PostModel(
            id=uuid4(),
            knowledge_unit_id=unit_id,
            content="Existing legacy post",
            status="DRAFT",
        )
        session.add(row)
        await session.commit()
        post = await ProducePost(FakeEditorialDrafter()).execute(session, unit_id)
        assert post.id != row.id
        rows = (await session.execute(
            select(PostModel).where(PostModel.knowledge_unit_id == unit_id)
        )).scalars().all()
        assert len(rows) == 2


class PromptRecordingDrafter:
    def __init__(self):
        self.prompts = []

    async def draft(self, *, title: str, content: str, source_name: str, pdf_slice: bytes | None = None, system_prompt: str | None = None) -> str:
        self.prompts.append(system_prompt)
        return content


async def test_runtime_uses_new_published_prompt_without_code_change(monkeypatch):
    key = "editorial.test." + str(uuid4())
    monkeypatch.setattr("app.application.posts.EDITORIAL_PROMPT_KEY", key)

    async with SessionFactory() as session:
        service = PromptTemplateService(session)
        _, version1 = await service.create_template(key, "Runtime test", "Resolver test", "PROMPT_V1")
        await service.publish(key, version1.version)

    _, _, unit1 = await _unit()
    drafter = PromptRecordingDrafter()
    async with SessionFactory() as session:
        await ProducePost(drafter, ControlPlaneResolver()).execute(session, unit1)
    assert drafter.prompts[-1] == "PROMPT_V1"

    async with SessionFactory() as session:
        version2 = await PromptTemplateService(session).create_draft(key, "PROMPT_V2")
        await PromptTemplateService(session).publish(key, version2.version)

    _, _, unit2 = await _unit()
    async with SessionFactory() as session:
        await ProducePost(drafter, ControlPlaneResolver()).execute(session, unit2)
    assert drafter.prompts[-1] == "PROMPT_V2"



async def test_independent_posts_keep_review_and_publication_references_separate() -> None:
    _, _, unit_id = await _unit()
    async with SessionFactory() as session:
        first = await ProducePost(FakeEditorialDrafter()).execute(session, unit_id)
        second = await ProducePost(FakeEditorialDrafter()).execute(session, unit_id)
        review = ReviewPost()
        first = await review.approve(session, first.id, "Approved independently")
        second = await review.reject(session, second.id, "Rejected independently")

        schedule = ScheduleModel(id=uuid4(), name="Independent post schedule", status="DRAFT", timezone="UTC")
        schedule_item = ScheduleItemModel(
            id=uuid4(), schedule_id=schedule.id, post_id=first.id, position=1,
            scheduled_at=datetime.now(timezone.utc), status="PENDING",
        )
        publication = PublicationModel(
            id=uuid4(), knowledge_unit_id=unit_id, post_id=first.id, platform="telegram",
            destination="test-destination", content=first.content, status="DRAFT",
        )
        session.add_all([schedule, schedule_item, publication])
        await session.commit()

        persisted_posts = {
            row.id: row
            for row in (await session.execute(
                select(PostModel).where(PostModel.id.in_([first.id, second.id]))
            )).scalars().all()
        }
        persisted_schedule_item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.id == schedule_item.id)
        )).scalar_one()
        persisted_publication = (await session.execute(
            select(PublicationModel).where(PublicationModel.id == publication.id)
        )).scalar_one()
        assert persisted_posts[first.id].status == "APPROVED"
        assert persisted_posts[second.id].status == "REJECTED"
        assert persisted_posts[first.id].review_note == "Approved independently"
        assert persisted_posts[second.id].review_note == "Rejected independently"
        assert persisted_schedule_item.post_id == first.id
        assert persisted_publication.post_id == first.id
        assert persisted_publication.content == first.content
