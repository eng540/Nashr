from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.extraction import IExtractor
from app.domain.knowledge import KnowledgeUnit
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel


class ExtractKnowledge:
    """Extract and persist exactly five knowledge units for a source."""

    def __init__(self, extractor: IExtractor) -> None:
        """Initialize the knowledge extraction use case."""
        self.extractor = extractor

    async def execute(self, session: AsyncSession, source_id: UUID) -> list[KnowledgeUnit]:
        """Extract exactly five ideas and persist their knowledge units."""
        source_result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
        source_model = source_result.scalar_one_or_none()
        if source_model is None:
            raise ValueError("Source not found.")
        ideas = await self.extractor.extract(source_model.to_domain())
        if len(ideas) != 5 or [idea.position for idea in ideas] != [1, 2, 3, 4, 5]:
            raise ValueError("Extractor must return exactly five ideas with positions 1 through 5.")
        existing = await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id))
        if existing.scalars().first() is not None:
            raise ValueError("Knowledge units already exist for this source.")
        units = [KnowledgeUnit.from_extracted(source_id, idea.position, idea.title, idea.content) for idea in ideas]
        session.add_all([
            KnowledgeUnitModel(
                id=unit.id,
                source_id=unit.source_id,
                position=unit.position,
                title=unit.title,
                content=unit.content,
                created_at=unit.created_at,
            )
            for unit in units
        ])
        await session.commit()
        return units
