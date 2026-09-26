from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import ExtractedIdea
from app.domain.knowledge import KnowledgeUnit
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel, TopicModel


class DiscoverBook:
    """Build a book map, discover topic-level materials, and persist the inventory."""

    def __init__(self, mapper, material_discoverer) -> None:
        self.mapper = mapper
        self.material_discoverer = material_discoverer

    async def execute(self, session: AsyncSession, source_id: UUID) -> tuple[BookMap, list[KnowledgeUnit]]:
        source_result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
        source = source_result.scalar_one_or_none()
        if source is None:
            raise ValueError("Source not found.")

        existing_topics = await session.execute(select(TopicModel).where(TopicModel.source_id == source_id))
        if existing_topics.scalars().first() is not None:
            raise ValueError("Book map already exists for this source.")

        mapped = await self.mapper.map_book(source.to_domain())
        if [topic.position for topic in mapped.topics] != list(range(1, len(mapped.topics) + 1)):
            raise ValueError("Book mapper must return topic positions starting at 1.")

        source.book_title = mapped.title
        source.book_description = mapped.description
        topics: list[BookTopic] = []
        for item in mapped.topics:
            topic = BookTopic.create(source_id, item.position, item.title, item.description, item.source_reference)
            topics.append(topic)
            session.add(TopicModel(id=topic.id, source_id=topic.source_id, position=topic.position, title=topic.title, description=topic.description, source_reference=topic.source_reference))
        await session.flush()

        all_units: list[KnowledgeUnit] = []
        seen: set[tuple[UUID, str]] = set()
        next_position = 1
        for topic in topics:
            ideas = await self.material_discoverer.discover_topic(source.to_domain(), topic)
            for idea in ideas:
                key_text = (idea.original_text or idea.content).strip().casefold()
                if not key_text:
                    continue
                key = (topic.id, key_text)
                if key in seen:
                    continue
                seen.add(key)
                unit = KnowledgeUnit.from_extracted(
                    source_id=source_id,
                    position=next_position,
                    title=idea.title,
                    content=idea.content,
                    original_text=idea.original_text,
                    source_reference=idea.source_reference,
                    topic_id=topic.id,
                    kind=idea.kind,
                )
                next_position += 1
                all_units.append(unit)
                session.add(KnowledgeUnitModel(
                    id=unit.id, source_id=unit.source_id, topic_id=unit.topic_id, position=unit.position,
                    title=unit.title, kind=unit.kind, content=unit.content,
                    original_text=unit.original_text, source_reference=unit.source_reference,
                    created_at=unit.created_at,
                ))

        await session.commit()
        return BookMap(source_id=source_id, title=mapped.title, description=mapped.description, topics=topics), all_units
