import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.extraction.gemini import GeminiBookMapper, GeminiTopicMaterialDiscoverer
from app.application.discover_book import DiscoverBook
from app.domain.extraction import DocumentReference
from app.domain.sources import SourceStatus
from app.infrastructure.database.models import DiscoveryJobModel, KnowledgeUnitModel, SourceModel, TopicModel
from app.infrastructure.database.session import SessionFactory

logger = logging.getLogger(__name__)


class DiscoveryJobStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DiscoveryJobStage:
    PREPARING_DOCUMENT = "PREPARING_DOCUMENT"
    BUILDING_BOOK_MAP = "BUILDING_BOOK_MAP"
    DISCOVERING_MATERIALS = "DISCOVERING_MATERIALS"
    FINALIZING = "FINALIZING"


async def create_discovery_job(session: AsyncSession, source_id: UUID) -> DiscoveryJobModel:
    source_result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
    source = source_result.scalar_one_or_none()
    if source is None:
        raise ValueError("Source not found.")

    active_result = await session.execute(
        select(DiscoveryJobModel)
        .where(
            DiscoveryJobModel.source_id == source_id,
            DiscoveryJobModel.status.in_([DiscoveryJobStatus.QUEUED, DiscoveryJobStatus.RUNNING]),
        )
        .order_by(DiscoveryJobModel.created_at.desc())
    )
    active = active_result.scalars().first()
    if active is not None:
        return active

    completed_result = await session.execute(
        select(DiscoveryJobModel)
        .where(
            DiscoveryJobModel.source_id == source_id,
            DiscoveryJobModel.status == DiscoveryJobStatus.COMPLETED,
        )
        .order_by(DiscoveryJobModel.created_at.desc())
    )
    completed = completed_result.scalars().first()
    if completed is not None:
        return completed

    job = DiscoveryJobModel(
        id=uuid4(),
        source_id=source_id,
        status=DiscoveryJobStatus.QUEUED,
        stage=DiscoveryJobStage.PREPARING_DOCUMENT,
        retryable=True,
    )
    source.status = SourceStatus.STORED.value
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        active_result = await session.execute(
            select(DiscoveryJobModel)
            .where(
                DiscoveryJobModel.source_id == source_id,
                DiscoveryJobModel.status.in_([DiscoveryJobStatus.QUEUED, DiscoveryJobStatus.RUNNING]),
            )
            .order_by(DiscoveryJobModel.created_at.desc())
        )
        active = active_result.scalars().first()
        if active is None:
            raise
        return active
    await session.refresh(job)
    return job


async def retry_discovery_job(session: AsyncSession, source_id: UUID) -> DiscoveryJobModel:
    result = await session.execute(
        select(DiscoveryJobModel)
        .where(
            DiscoveryJobModel.source_id == source_id,
            DiscoveryJobModel.status == DiscoveryJobStatus.FAILED,
        )
        .order_by(DiscoveryJobModel.created_at.desc())
    )
    job = result.scalars().first()
    if job is None:
        raise ValueError("No failed discovery job exists for this source.")

    active_result = await session.execute(
        select(DiscoveryJobModel)
        .where(
            DiscoveryJobModel.source_id == source_id,
            DiscoveryJobModel.status.in_([DiscoveryJobStatus.QUEUED, DiscoveryJobStatus.RUNNING]),
        )
    )
    if active_result.scalars().first() is not None:
        raise ValueError("A discovery job is already running for this source.")

    await session.execute(
        update(TopicModel)
        .where(
            TopicModel.source_id == source_id,
            TopicModel.discovery_status.in_(["FAILED", "RUNNING"]),
        )
        .values(discovery_status="PENDING", discovery_error=None)
    )
    job.status = DiscoveryJobStatus.QUEUED
    job.stage = DiscoveryJobStage.PREPARING_DOCUMENT
    job.error_message = None
    job.retryable = True
    job.current_topic_id = None
    job.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(job)
    return job


async def _claim_job(job_id: UUID) -> bool:
    async with SessionFactory() as session:
        result = await session.execute(
            update(DiscoveryJobModel)
            .where(
                DiscoveryJobModel.id == job_id,
                DiscoveryJobModel.status == DiscoveryJobStatus.QUEUED,
            )
            .values(
                status=DiscoveryJobStatus.RUNNING,
                stage=DiscoveryJobStage.PREPARING_DOCUMENT,
                attempts=DiscoveryJobModel.attempts + 1,
                started_at=func.now(),
                updated_at=func.now(),
                error_message=None,
            )
        )
        await session.commit()
        return result.rowcount == 1


async def _update_job(job_id: UUID, **values) -> None:
    values["updated_at"] = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        await session.execute(update(DiscoveryJobModel).where(DiscoveryJobModel.id == job_id).values(**values))
        await session.commit()


async def _progress(job_id: UUID, source_id: UUID, current_topic_id: UUID | None = None) -> None:
    async with SessionFactory() as session:
        completed_result = await session.execute(
            select(func.count(TopicModel.id)).where(
                TopicModel.source_id == source_id,
                TopicModel.discovery_status == "COMPLETED",
            )
        )
        material_result = await session.execute(
            select(func.count(KnowledgeUnitModel.id)).where(KnowledgeUnitModel.source_id == source_id)
        )
        await session.execute(
            update(DiscoveryJobModel)
            .where(DiscoveryJobModel.id == job_id)
            .values(
                topics_completed=int(completed_result.scalar_one() or 0),
                materials_discovered=int(material_result.scalar_one() or 0),
                current_topic_id=current_topic_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


class DiscoveryJobRunner:
    """Run durable discovery work independently of the HTTP request lifecycle."""

    def __init__(self, mapper, material_discoverer) -> None:
        self.discoverer = DiscoverBook(mapper, material_discoverer)

    async def run(self, job_id: UUID) -> None:
        if not await _claim_job(job_id):
            return

        try:
            async with SessionFactory() as session:
                job_result = await session.execute(select(DiscoveryJobModel).where(DiscoveryJobModel.id == job_id))
                job = job_result.scalar_one_or_none()
                if job is None:
                    return
                source_id = job.source_id

            await _update_job(job_id, stage=DiscoveryJobStage.PREPARING_DOCUMENT)
            async with SessionFactory() as session:
                document: DocumentReference = await self.discoverer.prepare_document(session, source_id)

            await _update_job(job_id, stage=DiscoveryJobStage.BUILDING_BOOK_MAP)
            async with SessionFactory() as session:
                book_map = await self.discoverer.build_book_map(session, source_id, document)
            await _update_job(job_id, topics_total=len(book_map.topics))

            await _update_job(job_id, stage=DiscoveryJobStage.DISCOVERING_MATERIALS)
            for topic in book_map.topics:
                async with SessionFactory() as session:
                    topic_row = (
                        await session.execute(
                            select(TopicModel).where(TopicModel.id == topic.id, TopicModel.source_id == source_id)
                        )
                    ).scalar_one()

                if topic_row.discovery_status == "COMPLETED":
                    await _progress(job_id, source_id, None)
                    continue

                await _update_job(job_id, current_topic_id=topic.id)
                async with SessionFactory() as session:
                    await self.discoverer.discover_topic(session, source_id, topic.id, document)
                await _progress(job_id, source_id, None)

            await _update_job(
                job_id,
                stage=DiscoveryJobStage.FINALIZING,
                current_topic_id=None,
            )
            async with SessionFactory() as session:
                source_result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
                source = source_result.scalar_one()
                source.status = SourceStatus.EXTRACTED.value
                await session.commit()

            await _update_job(
                job_id,
                status=DiscoveryJobStatus.COMPLETED,
                stage=DiscoveryJobStage.FINALIZING,
                current_topic_id=None,
                completed_at=datetime.now(timezone.utc),
                error_message=None,
                retryable=False,
            )
            logger.info("discovery_job_completed job_id=%s source_id=%s", job_id, source_id)
        except Exception as exc:
            logger.exception("discovery_job_failed job_id=%s", job_id)
            async with SessionFactory() as session:
                job_result = await session.execute(select(DiscoveryJobModel).where(DiscoveryJobModel.id == job_id))
                job = job_result.scalar_one_or_none()
                if job is not None:
                    retryable = not isinstance(exc, (ValueError, FileNotFoundError))
                    if job.current_topic_id:
                        await session.execute(
                            update(TopicModel)
                            .where(TopicModel.id == job.current_topic_id)
                            .values(
                                discovery_status="FAILED",
                                discovery_error=f"Discovery failed during {job.stage}.",
                            )
                        )
                    await session.execute(
                        update(SourceModel)
                        .where(SourceModel.id == job.source_id)
                        .values(status=SourceStatus.FAILED.value)
                    )
                    await session.execute(
                        update(DiscoveryJobModel)
                        .where(DiscoveryJobModel.id == job_id)
                        .values(
                            status=DiscoveryJobStatus.FAILED,
                            error_message=f"تعذر إكمال الاستكشاف أثناء المرحلة الحالية. يمكن إعادة المحاولة: {'نعم' if retryable else 'لا'}.",
                            retryable=retryable,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()


async def run_discovery_job(job_id: UUID) -> None:
    """Default production executor; creates its own adapters and DB resources."""
    await DiscoveryJobRunner(GeminiBookMapper(), GeminiTopicMaterialDiscoverer()).run(job_id)
