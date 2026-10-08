from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.adapters.drafting.fake import FakeEditorialDrafter
from app.application.posts import ProducePost
from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, SourceModel, TopicModel
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


async def test_produce_post_is_idempotent() -> None:
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


async def test_existing_post_is_returned_without_regeneration() -> None:
    _, _, unit_id = await _unit()
    async with SessionFactory() as session:
        row = PostModel(
            id=uuid4(),
            knowledge_unit_id=unit_id,
            content="Existing post",
            status="DRAFT",
        )
        session.add(row)
        await session.commit()
        post = await ProducePost(FailingDrafter()).execute(session, unit_id)
        assert post.id == row.id
        assert post.content == "Existing post"
