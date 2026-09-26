import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.extraction.gemini import GeminiBookMapper, GeminiOperationError, GeminiTopicMaterialDiscoverer
from app.application.discover_book import DiscoverBook
from app.domain.extraction import DocumentReference
from app.domain.sources import SourceStatus
from app.infrastructure.database.models import (
    DiscoveryChunkModel,
    DiscoveryJobModel,
    KnowledgeUnitModel,
    SourceModel,
    TopicModel,
)
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
    source = (
        await session.execute(select(SourceModel).where(SourceModel.id == source_id))
    ).scalar_one_or_none()
    if source is None:
        raise ValueError("Source not found.")

    active = (
        await session.execute(
            select(DiscoveryJobModel)
            .where(
                DiscoveryJobModel.source_id == source_id,
                DiscoveryJobModel.status.in_([DiscoveryJobStatus.QUEUED, DiscoveryJobStatus.RUNNING]),
            )
            .order_by(DiscoveryJobModel.created_at.desc())
        )
    ).scalars().first()
    if active is not None:
        return active

    completed = (
        await session.execute(
            select(DiscoveryJobModel)
            .where(
                DiscoveryJobModel.source_id == source_id,
                DiscoveryJobModel.status == DiscoveryJobStatus.COMPLETED,
            )
            .order_by(DiscoveryJobModel.created_at.desc())
        )
    ).scalars().first()
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
        active = (
            await session.execute(
                select(DiscoveryJobModel)
                .where(
                    DiscoveryJobModel.source_id == source_id,
                    DiscoveryJobModel.status.in_([DiscoveryJobStatus.QUEUED, DiscoveryJobStatus.RUNNING]),
                )
                .order_by(DiscoveryJobModel.created_at.desc())
            )
        ).scalars().first()
        if active is None:
            raise
        return active
    await session.refresh(job)
    logger.info("event=DISCOVERY_CREATED job_id=%s source_id=%s", job.id, source_id)
    return job


async def retry_discovery_job(session: AsyncSession, source_id: UUID) -> DiscoveryJobModel:
    job = (
        await session.execute(
            select(DiscoveryJobModel)
            .where(
                DiscoveryJobModel.source_id == source_id,
                DiscoveryJobModel.status == DiscoveryJobStatus.FAILED,
            )
            .order_by(DiscoveryJobModel.created_at.desc())
        )
    ).scalars().first()
    if job is None:
        raise ValueError("No failed discovery job exists for this source.")

    active = (
        await session.execute(
            select(DiscoveryJobModel).where(
                DiscoveryJobModel.source_id == source_id,
                DiscoveryJobModel.status.in_([DiscoveryJobStatus.QUEUED, DiscoveryJobStatus.RUNNING]),
            )
        )
    ).scalars().first()
    if active is not None:
        raise ValueError("A discovery job is already running for this source.")

    await session.execute(
        update(TopicModel)
        .where(
            TopicModel.source_id == source_id,
            TopicModel.discovery_status.in_(["FAILED", "RUNNING"]),
        )
        .values(discovery_status="PENDING", discovery_error=None)
    )
    await session.execute(
        update(DiscoveryChunkModel)
        .where(
            DiscoveryChunkModel.topic_id.in_(
                select(TopicModel.id).where(TopicModel.source_id == source_id)
            ),
            DiscoveryChunkModel.status.in_(["FAILED", "RUNNING"]),
        )
        .values(status="PENDING", error_code=None, error_message=None)
    )
    job.status = DiscoveryJobStatus.QUEUED
    job.stage = DiscoveryJobStage.PREPARING_DOCUMENT
    job.error_code = None
    job.error_message = None
    job.retryable = True
    job.current_topic_id = None
    job.current_chunk_id = None
    job.completed_at = None
    job.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(job)
    logger.info("event=DISCOVERY_RETRY job_id=%s source_id=%s", job.id, source_id)
    return job


async def recover_stale_jobs() -> list[UUID]:
    threshold = datetime.now(timezone.utc) - timedelta(
        seconds=int(os.getenv("NASHR_DISCOVERY_STALE_SECONDS", "900"))
    )
    recovered: list[UUID] = []
    async with SessionFactory() as session:
        jobs = (
            await session.execute(
                select(DiscoveryJobModel).where(
                    DiscoveryJobModel.status == DiscoveryJobStatus.RUNNING,
                    DiscoveryJobModel.updated_at < threshold,
                )
            )
        ).scalars().all()
        for job in jobs:
            await session.execute(
                update(DiscoveryChunkModel)
                .where(
                    DiscoveryChunkModel.topic_id.in_(
                        select(TopicModel.id).where(TopicModel.source_id == job.source_id)
                    ),
                    DiscoveryChunkModel.status == "RUNNING",
                )
                .values(status="PENDING", error_code=None, error_message=None)
            )
            await session.execute(
                update(TopicModel)
                .where(
                    TopicModel.source_id == job.source_id,
                    TopicModel.discovery_status == "RUNNING",
                )
                .values(discovery_status="PENDING", discovery_error=None)
            )
            job.status = DiscoveryJobStatus.QUEUED
            job.current_topic_id = None
            job.current_chunk_id = None
            job.error_code = "DISCOVERY_RECOVERED_AFTER_PROCESS_STALE"
            job.error_message = "Recovered after the previous process stopped before completion."
            job.retryable = True
            job.updated_at = datetime.now(timezone.utc)
            recovered.append(job.id)
        await session.commit()
    for job_id in recovered:
        logger.warning("event=DISCOVERY_RECOVERED job_id=%s", job_id)
    return recovered


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
                error_code=None,
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


async def _progress(job_id: UUID, source_id: UUID, current_topic_id: UUID | None = None, current_chunk_id: UUID | None = None) -> None:
    async with SessionFactory() as session:
        topics_completed = int(
            (
                await session.execute(
                    select(func.count(TopicModel.id)).where(
                        TopicModel.source_id == source_id,
                        TopicModel.discovery_status == "COMPLETED",
                    )
                )
            ).scalar_one()
            or 0
        )
        chunks_completed = int(
            (
                await session.execute(
                    select(func.count(DiscoveryChunkModel.id))
                    .join(TopicModel, TopicModel.id == DiscoveryChunkModel.topic_id)
                    .where(
                        TopicModel.source_id == source_id,
                        DiscoveryChunkModel.status == "COMPLETED",
                    )
                )
            ).scalar_one()
            or 0
        )
        materials = int(
            (
                await session.execute(
                    select(func.count(KnowledgeUnitModel.id)).where(KnowledgeUnitModel.source_id == source_id)
                )
            ).scalar_one()
            or 0
        )
        await session.execute(
            update(DiscoveryJobModel)
            .where(DiscoveryJobModel.id == job_id)
            .values(
                topics_completed=topics_completed,
                chunks_completed=chunks_completed,
                materials_discovered=materials,
                current_topic_id=current_topic_id,
                current_chunk_id=current_chunk_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


class DiscoveryJobRunner:
    """Run durable sequential discovery work independently of the HTTP request lifecycle."""

    def __init__(self, mapper, material_discoverer) -> None:
        self.discoverer = DiscoverBook(mapper, material_discoverer)

    async def run(self, job_id: UUID) -> None:
        if not await _claim_job(job_id):
            return
        logger.info("event=DISCOVERY_STARTED job_id=%s", job_id)

        try:
            async with SessionFactory() as session:
                job = (
                    await session.execute(select(DiscoveryJobModel).where(DiscoveryJobModel.id == job_id))
                ).scalar_one_or_none()
                if job is None:
                    return
                source_id = job.source_id
                source = (
                    await session.execute(select(SourceModel).where(SourceModel.id == source_id))
                ).scalar_one()
                source.status = SourceStatus.EXTRACTING.value
                await session.commit()

            await _update_job(job_id, stage=DiscoveryJobStage.PREPARING_DOCUMENT)
            async with SessionFactory() as session:
                document: DocumentReference = await self.discoverer.prepare_document(session, source_id)

            await _update_job(job_id, stage=DiscoveryJobStage.BUILDING_BOOK_MAP)
            async with SessionFactory() as session:
                book_map = await self.discoverer.build_book_map(session, source_id, document)

            topics_total = len(book_map.topics)
            chunks_total = 0
            for topic in book_map.topics:
                async with SessionFactory() as session:
                    chunks = await self.discoverer.ensure_topic_chunks(session, topic.id)
                    chunks_total += len(chunks)
            await _update_job(
                job_id,
                topics_total=topics_total,
                chunks_total=chunks_total,
                stage=DiscoveryJobStage.DISCOVERING_MATERIALS,
            )

            for topic in book_map.topics:
                async with SessionFactory() as session:
                    chunks = await self.discoverer.ensure_topic_chunks(session, topic.id)
                for chunk in chunks:
                    if chunk.status == "COMPLETED":
                        await _progress(job_id, source_id)
                        continue
                    await _update_job(
                        job_id,
                        current_topic_id=topic.id,
                        current_chunk_id=chunk.id,
                    )
                    async with SessionFactory() as session:
                        await self.discoverer.discover_chunk(
                            session,
                            source_id,
                            topic.id,
                            chunk.id,
                            document,
                        )
                    await _progress(job_id, source_id)

            await _update_job(
                job_id,
                stage=DiscoveryJobStage.FINALIZING,
                current_topic_id=None,
                current_chunk_id=None,
            )
            async with SessionFactory() as session:
                source = (
                    await session.execute(select(SourceModel).where(SourceModel.id == source_id))
                ).scalar_one()
                source.status = SourceStatus.EXTRACTED.value
                await session.commit()

            await _update_job(
                job_id,
                status=DiscoveryJobStatus.COMPLETED,
                stage=DiscoveryJobStage.FINALIZING,
                completed_at=datetime.now(timezone.utc),
                error_code=None,
                error_message=None,
                retryable=False,
                current_topic_id=None,
                current_chunk_id=None,
            )
            logger.info("event=DISCOVERY_COMPLETED job_id=%s source_id=%s", job_id, source_id)
        except Exception as exc:
            logger.exception("event=DISCOVERY_FAILED job_id=%s", job_id)
            code = getattr(exc, "code", None)
            retryable = getattr(exc, "retryable", None)
            if code is None:
                if isinstance(exc, (ValueError, FileNotFoundError)):
                    code, retryable = "DISCOVERY_DATA_ERROR", False
                else:
                    code, retryable = "UNKNOWN", True
            async with SessionFactory() as session:
                job = (
                    await session.execute(select(DiscoveryJobModel).where(DiscoveryJobModel.id == job_id))
                ).scalar_one_or_none()
                if job is None:
                    return
                if job.current_chunk_id:
                    await session.execute(
                        update(DiscoveryChunkModel)
                        .where(DiscoveryChunkModel.id == job.current_chunk_id)
                        .values(
                            status="FAILED",
                            error_code=code,
                            error_message=str(exc),
                        )
                    )
                if job.current_topic_id:
                    await session.execute(
                        update(TopicModel)
                        .where(TopicModel.id == job.current_topic_id)
                        .values(
                            discovery_status="FAILED",
                            discovery_error=f"Discovery failed: {code}.",
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
                        error_code=code,
                        error_message=f"Discovery failed with {code}. Retryable: {'yes' if retryable else 'no'}.",
                        retryable=bool(retryable),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()


async def run_discovery_job(job_id: UUID) -> None:
    await DiscoveryJobRunner(GeminiBookMapper(), GeminiTopicMaterialDiscoverer()).run(job_id)
