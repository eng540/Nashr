import pytest
from sqlalchemy import select
from uuid import uuid4

from app.adapters.drafting.fake import FakeEditorialDrafter
from app.adapters.extraction.fake import FakeBookMapper, FakeTopicMaterialDiscoverer
from app.application.discover_book import DiscoverBook
from app.application.publications import CreateTelegramDraft
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel, TopicModel
from app.infrastructure.database.session import SessionFactory


@pytest.mark.parametrize("count", [0, 1, 5, 6, 17])
async def test_hierarchical_discovery_supports_zero_and_arbitrary_counts(count: int) -> None:
    source_id = uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(id=source_id, filename="book.pdf", mime_type="application/pdf", storage_path="./storage/test/book.pdf", size_bytes=10, status="STORED", content_sha256="test-hash"))
        await session.commit()
        book_map, units = await DiscoverBook(FakeBookMapper(), FakeTopicMaterialDiscoverer(count)).execute(session, source_id)
        assert book_map.title == "book.pdf"
        assert len(book_map.topics) == 1
        assert len(units) == count
        assert [u.position for u in units] == list(range(1, count + 1))
        assert all(u.topic_id == book_map.topics[0].id for u in units)


async def test_hierarchical_material_keeps_kind_provenance_and_drafts() -> None:
    source_id = uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(id=source_id, filename="book.pdf", mime_type="application/pdf", storage_path="./storage/test/book.pdf", size_bytes=10, status="STORED", content_sha256="test-hash"))
        await session.commit()
        book_map, units = await DiscoverBook(FakeBookMapper(), FakeTopicMaterialDiscoverer(2)).execute(session, source_id)
        first = units[0]
        assert first.kind == "حكمة"
        assert first.original_text == "Original topic text 1"
        assert first.source_reference == "pages 1-1"
        row = (await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.id == first.id))).scalar_one()
        assert row.topic_id == book_map.topics[0].id
        draft = await CreateTelegramDraft(FakeEditorialDrafter()).execute(session, first.id, "@test")
        assert draft.status.value == "DRAFT"


async def test_topic_order_is_deterministic() -> None:
    source_id = uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(id=source_id, filename="book.pdf", mime_type="application/pdf", storage_path="./storage/test/book.pdf", size_bytes=10, status="STORED", content_sha256="test-hash"))
        await session.commit()
        book_map, _ = await DiscoverBook(FakeBookMapper(), FakeTopicMaterialDiscoverer(0)).execute(session, source_id)
        rows = (await session.execute(select(TopicModel).where(TopicModel.source_id == source_id).order_by(TopicModel.position))).scalars().all()
        assert [t.position for t in rows] == [1]
        assert rows[0].id == book_map.topics[0].id
