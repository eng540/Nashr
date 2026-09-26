from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.extraction import IExtractor
from app.domain.knowledge import KnowledgeUnit
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel


class ExtractKnowledge:
    """Discover and persist zero or more knowledge units for a source."""

    def __init__(self, extractor: IExtractor) -> None:
        """Initialize the knowledge discovery use case."""
        self.extractor = extractor

    async def execute(self, session: AsyncSession, source_id: UUID) -> list[KnowledgeUnit]:
        """Discover and persist all materials returned by the extractor."""
        source_result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
        source_model = source_result.scalar_one_or_none()
        if source_model is None:
            raise ValueError("Source not found.")
        ideas = await self.extractor.extract(source_model.to_domain())
        positions = [idea.position for idea in ideas]
        if positions != list(range(1, len(ideas) + 1)):
            raise ValueError("Extractor must return materials with positions starting at 1 in discovery order.")
        existing = await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id))
        if existing.scalars().first() is not None:
            raise ValueError("Knowledge units already exist for this source.")
        units = [
            KnowledgeUnit.from_extracted(
                source_id,
                idea.position,
                idea.title,
                idea.content,
                idea.original_text,
                idea.source_reference,
            )
            for idea in ideas
        ]
        session.add_all([
            KnowledgeUnitModel(
                id=unit.id,
                source_id=unit.source_id,
                position=unit.position,
                title=unit.title,
                content=unit.content,
                original_text=unit.original_text,
                source_reference=unit.source_reference,
                created_at=unit.created_at,
            )
            for unit in units
        ])
        await session.commit()
        return units
