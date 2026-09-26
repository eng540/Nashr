import hashlib
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import DocumentReference, ExtractedIdea
from app.domain.knowledge import KnowledgeUnit
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel, TopicModel


class DiscoverBook:
    """Build a durable hierarchical inventory with reusable document input and checkpoints."""

    def __init__(self, mapper, material_discoverer) -> None:
        self.mapper = mapper
        self.material_discoverer = material_discoverer

    async def get_source(self, session: AsyncSession, source_id: UUID) -> SourceModel:
        result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
        source = result.scalar_one_or_none()
        if source is None:
            raise ValueError("Source not found.")
        return source

    async def prepare_document(self, session: AsyncSession, source_id: UUID) -> DocumentReference:
        source = await self.get_source(session, source_id)
        if not source.content_sha256:
            path = Path(source.storage_path)
            if not path.is_file():
                raise FileNotFoundError(source.storage_path)
            source.content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            await session.commit()
            await session.refresh(source)

        document = await self.mapper.prepare_document(source.to_domain())
        source.gemini_file_name = document.name
        source.gemini_file_uri = document.uri
        source.gemini_file_mime_type = document.mime_type
        source.gemini_file_source_sha256 = source.content_sha256
        await session.commit()
        return document

    async def build_book_map(self, session: AsyncSession, source_id: UUID, document: DocumentReference) -> BookMap:
        source = await self.get_source(session, source_id)
        existing_result = await session.execute(
            select(TopicModel).where(TopicModel.source_id == source_id).order_by(TopicModel.position)
        )
        existing = existing_result.scalars().all()
        if existing:
            return BookMap(
                source_id=source_id,
                title=source.book_title or source.filename,
                description=source.book_description or "",
                topics=[
                    BookTopic(topic.id, topic.source_id, topic.position, topic.title, topic.description, topic.source_reference)
                    for topic in existing
                ],
            )

        mapped = await self.mapper.map_book(source.to_domain(), document)
        if [topic.position for topic in mapped.topics] != list(range(1, len(mapped.topics) + 1)):
            raise ValueError("Gemini returned invalid topic positions.")

        source.book_title = mapped.title
        source.book_description = mapped.description
        for item in mapped.topics:
            session.add(
                TopicModel(
                    id=item.id,
                    source_id=source_id,
                    position=item.position,
                    title=item.title,
                    description=item.description,
                    source_reference=item.source_reference,
                    discovery_status="PENDING",
                )
            )
        await session.commit()
        return mapped

    async def discover_topic(
        self,
        session: AsyncSession,
        source_id: UUID,
        topic_id: UUID,
        document: DocumentReference,
    ) -> int:
        topic_result = await session.execute(
            select(TopicModel).where(TopicModel.id == topic_id, TopicModel.source_id == source_id)
        )
        topic = topic_result.scalar_one_or_none()
        if topic is None:
            raise ValueError("Topic not found.")

        if topic.discovery_status == "COMPLETED":
            result = await session.execute(
                select(func.count(KnowledgeUnitModel.id)).where(KnowledgeUnitModel.topic_id == topic_id)
            )
            return int(result.scalar_one() or 0)

        topic.discovery_status = "RUNNING"
        topic.discovery_error = None
        await session.commit()

        try:
            source = await self.get_source(session, source_id)
            domain_topic = BookTopic(topic.id, topic.source_id, topic.position, topic.title, topic.description, topic.source_reference)
            ideas = await self.material_discoverer.discover_topic(source.to_domain(), domain_topic, document)

            existing_result = await session.execute(
                select(KnowledgeUnitModel).where(KnowledgeUnitModel.topic_id == topic_id)
            )
            existing_rows = existing_result.scalars().all()
            seen = {
                (row.original_text or row.content).strip().casefold()
                for row in existing_rows
                if (row.original_text or row.content).strip()
            }

            max_position_result = await session.execute(
                select(func.max(KnowledgeUnitModel.position)).where(KnowledgeUnitModel.source_id == source_id)
            )
            next_position = int(max_position_result.scalar_one() or 0) + 1
            discovered = 0

            for idea in ideas:
                key_text = (idea.original_text or idea.content).strip()
                if not key_text:
                    continue
                key = key_text.casefold()
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
                    topic_id=topic_id,
                    kind=idea.kind,
                )
                session.add(
                    KnowledgeUnitModel(
                        id=unit.id,
                        source_id=unit.source_id,
                        topic_id=unit.topic_id,
                        position=unit.position,
                        title=unit.title,
                        kind=unit.kind,
                        content=unit.content,
                        original_text=unit.original_text,
                        source_reference=unit.source_reference,
                        created_at=unit.created_at,
                    )
                )
                next_position += 1
                discovered += 1

            topic.discovery_status = "COMPLETED"
            topic.discovery_error = None
            await session.commit()
            return discovered
        except Exception as exc:
            topic.discovery_status = "FAILED"
            topic.discovery_error = f"{type(exc).__name__}: discovery failed for this topic."
            await session.commit()
            raise exc

    async def execute(self, session: AsyncSession, source_id: UUID) -> tuple[BookMap, list[KnowledgeUnit]]:
        """Backward-compatible synchronous application entry point for tests and scripts."""
        source = await self.get_source(session, source_id)
        existing_topics = await session.execute(select(TopicModel).where(TopicModel.source_id == source_id))
        if existing_topics.scalars().first() is not None:
            raise ValueError("Book map already exists for this source.")

        document = await self.prepare_document(session, source_id)
        book_map = await self.build_book_map(session, source_id, document)

        for topic in book_map.topics:
            await self.discover_topic(session, source_id, topic.id, document)

        result = await session.execute(
            select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id).order_by(KnowledgeUnitModel.position)
        )
        rows = result.scalars().all()
        units = [
            KnowledgeUnit(
                id=row.id,
                source_id=row.source_id,
                position=row.position,
                title=row.title,
                content=row.content,
                original_text=row.original_text,
                source_reference=row.source_reference,
                created_at=row.created_at,
                topic_id=row.topic_id,
                kind=row.kind,
            )
            for row in rows
        ]
        return book_map, units
