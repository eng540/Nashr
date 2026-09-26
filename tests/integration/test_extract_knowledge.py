from uuid import uuid4

from sqlalchemy import select

from app.adapters.extraction.fake import FakeExtractor
from app.application.extract_knowledge import ExtractKnowledge
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import SessionFactory


async def test_fake_extractor_persists_multiple_materials_and_provenance() -> None:
    """Verify the application persists multiple materials and their provenance."""
    source_id = uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(id=source_id, filename="ideas.pdf", mime_type="application/pdf", storage_path="./storage/test/ideas.pdf", size_bytes=10, status="STORED"))
        await session.commit()
        units = await ExtractKnowledge(FakeExtractor()).execute(session, source_id)
        assert len(units) == 5
        result = await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id).order_by(KnowledgeUnitModel.position))
        rows = result.scalars().all()
        assert len(rows) == 5
        assert [row.position for row in rows] == [1, 2, 3, 4, 5]
        assert rows[0].original_text == "Original mock text 1"
        assert rows[0].source_reference == "page 1"


async def test_empty_discovery_is_valid() -> None:
    """Verify a source may legitimately yield zero materials."""
    class EmptyExtractor:
        async def extract(self, source):
            return []

    source_id = uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(id=source_id, filename="empty.pdf", mime_type="application/pdf", storage_path="./storage/test/empty.pdf", size_bytes=10, status="STORED"))
        await session.commit()
        units = await ExtractKnowledge(EmptyExtractor()).execute(session, source_id)
        assert units == []
