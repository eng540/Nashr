import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.extraction.gemini import GeminiOperationError
from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import DiscoverySpan, DocumentReference, ExtractedIdea
from app.domain.knowledge import KnowledgeUnit
from app.infrastructure.database.models import DiscoveryChunkModel, KnowledgeUnitModel, SourceModel, TopicModel


class DiscoverBook:
    """Build a durable hierarchical inventory with bounded document checkpoints."""

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
        existing = (
            await session.execute(
                select(TopicModel).where(TopicModel.source_id == source_id).order_by(TopicModel.position)
            )
        ).scalars().all()

        if existing and all(topic.page_start and topic.page_end for topic in existing):
            return BookMap(
                source_id=source_id,
                title=source.book_title or source.filename,
                description=source.book_description or "",
                topics=[
                    BookTopic(
                        topic.id,
                        topic.source_id,
                        topic.position,
                        topic.title,
                        topic.description,
                        topic.source_reference,
                        topic.page_start,
                        topic.page_end,
                    )
                    for topic in existing
                ],
            )

        mapped = await self.mapper.map_book(source.to_domain(), document)
        if [topic.position for topic in mapped.topics] != list(range(1, len(mapped.topics) + 1)):
            raise GeminiOperationError("GEMINI_SCHEMA_ERROR", "Gemini returned invalid topic positions.")
        if any(topic.page_start is None or topic.page_end is None for topic in mapped.topics):
            raise GeminiOperationError(
                "GEMINI_PROVENANCE_UNAVAILABLE",
                "Gemini did not provide evidence-backed page bounds for every topic.",
            )

        existing_units = int(
            (await session.execute(select(func.count(KnowledgeUnitModel.id)).where(KnowledgeUnitModel.source_id == source_id))).scalar_one()
            or 0
        )
        if existing and existing_units and len(existing) != len(mapped.topics):
            raise GeminiOperationError(
                "DISCOVERY_DATA_ERROR",
                "Existing material inventory cannot be safely reconciled with a changed topic map.",
            )

        source.book_title = mapped.title
        source.book_description = mapped.description
        if existing:
            by_position = {topic.position: topic for topic in existing}
            for item in mapped.topics:
                row = by_position.get(item.position)
                if row is None:
                    raise GeminiOperationError("DISCOVERY_DATA_ERROR", "Topic map changed incompatibly.")
                row.title = item.title
                row.description = item.description
                row.source_reference = item.source_reference
                row.page_start = item.page_start
                row.page_end = item.page_end
                row.discovery_status = "PENDING" if not row.discovery_status == "COMPLETED" else row.discovery_status
        else:
            for item in mapped.topics:
                session.add(
                    TopicModel(
                        id=item.id,
                        source_id=source_id,
                        position=item.position,
                        title=item.title,
                        description=item.description,
                        source_reference=item.source_reference,
                        page_start=item.page_start,
                        page_end=item.page_end,
                        discovery_status="PENDING",
                    )
                )
        await session.commit()
        return mapped

    async def ensure_topic_chunks(self, session: AsyncSession, topic_id: UUID) -> list[DiscoveryChunkModel]:
        topic = (
            await session.execute(select(TopicModel).where(TopicModel.id == topic_id))
        ).scalar_one_or_none()
        if topic is None:
            raise ValueError("Topic not found.")
        if not topic.page_start or not topic.page_end or topic.page_start > topic.page_end:
            raise GeminiOperationError("GEMINI_PROVENANCE_UNAVAILABLE", "Topic has no valid page bounds.")

        existing = (
            await session.execute(
                select(DiscoveryChunkModel)
                .where(DiscoveryChunkModel.topic_id == topic_id)
                .order_by(DiscoveryChunkModel.chunk_index)
            )
        ).scalars().all()
        if existing:
            return existing

        max_pages = max(1, int(os.getenv("GEMINI_DISCOVERY_MAX_PAGES_PER_CHUNK", "8")))
        rows: list[DiscoveryChunkModel] = []
        start = topic.page_start
        index = 1
        while start <= topic.page_end:
            end = min(start + max_pages - 1, topic.page_end)
            row = DiscoveryChunkModel(
                id=uuid4(),
                topic_id=topic_id,
                chunk_index=index,
                page_start=start,
                page_end=end,
                status="PENDING",
            )
            session.add(row)
            rows.append(row)
            start = end + 1
            index += 1
        await session.commit()
        return rows

    async def discover_chunk(
        self,
        session: AsyncSession,
        source_id: UUID,
        topic_id: UUID,
        chunk_id: UUID,
        document: DocumentReference,
    ) -> int:
        chunk = (
            await session.execute(
                select(DiscoveryChunkModel)
                .where(DiscoveryChunkModel.id == chunk_id, DiscoveryChunkModel.topic_id == topic_id)
            )
        ).scalar_one_or_none()
        topic = (
            await session.execute(
                select(TopicModel).where(TopicModel.id == topic_id, TopicModel.source_id == source_id)
            )
        ).scalar_one_or_none()
        if chunk is None or topic is None:
            raise ValueError("Discovery chunk or topic not found.")

        if chunk.status == "COMPLETED":
            return 0

        chunk.status = "RUNNING"
        chunk.error_code = None
        chunk.error_message = None
        topic.discovery_status = "RUNNING"
        topic.discovery_error = None
        await session.commit()

        try:
            source = await self.get_source(session, source_id)
            domain_topic = BookTopic(
                topic.id,
                topic.source_id,
                topic.position,
                topic.title,
                topic.description,
                topic.source_reference,
                topic.page_start,
                topic.page_end,
            )
            ideas = await self.material_discoverer.discover_topic(
                source.to_domain(),
                domain_topic,
                document,
                DiscoverySpan(chunk.page_start, chunk.page_end, chunk.chunk_index),
            )

            existing_rows = (
                await session.execute(
                    select(KnowledgeUnitModel).where(KnowledgeUnitModel.topic_id == topic_id)
                )
            ).scalars().all()
            seen = {
                (row.original_text or row.content).strip().casefold()
                for row in existing_rows
                if (row.original_text or row.content).strip()
            }

            max_position = int(
                (
                    await session.execute(
                        select(func.max(KnowledgeUnitModel.position)).where(KnowledgeUnitModel.source_id == source_id)
                    )
                ).scalar_one()
                or 0
            )
            next_position = max_position + 1
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
                        discovery_page_start=chunk.page_start,
                        discovery_page_end=chunk.page_end,
                        discovery_chunk_index=chunk.chunk_index,
                        created_at=unit.created_at,
                    )
                )
                next_position += 1
                discovered += 1

            chunk.status = "COMPLETED"
            await session.commit()

            remaining = int(
                (
                    await session.execute(
                        select(func.count(DiscoveryChunkModel.id)).where(
                            DiscoveryChunkModel.topic_id == topic_id,
                            DiscoveryChunkModel.status != "COMPLETED",
                        )
                    )
                ).scalar_one()
                or 0
            )
            if remaining == 0:
                topic.discovery_status = "COMPLETED"
                topic.discovery_error = None
                await session.commit()
            return discovered
        except Exception as exc:
            if isinstance(exc, GeminiOperationError):
                chunk.error_code = exc.code
                chunk.error_message = str(exc)
            else:
                chunk.error_code = "DISCOVERY_DATA_ERROR"
                chunk.error_message = f"{type(exc).__name__}: discovery failed."
            chunk.status = "FAILED"
            topic.discovery_status = "FAILED"
            topic.discovery_error = f"Discovery failed for chunk {chunk.chunk_index}."
            await session.commit()
            raise

    async def execute(self, session: AsyncSession, source_id: UUID) -> tuple[BookMap, list[KnowledgeUnit]]:
        """Backward-compatible application entry point; executes the new bounded lifecycle sequentially."""
        source = await self.get_source(session, source_id)
        document = await self.prepare_document(session, source_id)
        book_map = await self.build_book_map(session, source_id, document)

        for topic in book_map.topics:
            chunks = await self.ensure_topic_chunks(session, topic.id)
            for chunk in chunks:
                await self.discover_chunk(session, source_id, topic.id, chunk.id, document)

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
