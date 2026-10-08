import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.application.control_plane import ControlPlaneResolver, EDITORIAL_PROMPT_KEY
from app.application.posts import ProducePost
from app.application.artifacts import post_to_artifact
from app.domain.production_jobs import (
    ProductionJobItemStatus,
    ProductionJobStatus,
    ProductionScope,
)
from app.infrastructure.database.models import (
    KnowledgeUnitModel,
    PostModel,
    ProductionJobItemModel,
    ProductionJobModel,
    SourceModel,
    TopicModel,
)
from app.infrastructure.database.session import SessionFactory

logger = logging.getLogger(__name__)


def _stale_seconds() -> int:
    return int(os.getenv("NASHR_PRODUCTION_STALE_SECONDS", "900"))


async def _resolve_units(
    session: AsyncSession,
    source_id: UUID,
    scope: ProductionScope,
    topic_id: UUID | None,
    knowledge_unit_ids: list[UUID],
) -> list[KnowledgeUnitModel]:
    source = (
        await session.execute(select(SourceModel).where(SourceModel.id == source_id))
    ).scalar_one_or_none()
    if source is None:
        raise ValueError("Source not found.")

    if scope == ProductionScope.SOURCE:
        if topic_id is not None or knowledge_unit_ids:
            raise ValueError("SOURCE scope accepts only source_id.")
        query = (
            select(KnowledgeUnitModel)
            .where(KnowledgeUnitModel.source_id == source_id)
            .order_by(KnowledgeUnitModel.position, KnowledgeUnitModel.id)
        )
    elif scope == ProductionScope.TOPIC:
        if topic_id is None or knowledge_unit_ids:
            raise ValueError("TOPIC scope requires topic_id and no explicit selection.")
        topic = (
            await session.execute(
                select(TopicModel).where(
                    TopicModel.id == topic_id,
                    TopicModel.source_id == source_id,
                )
            )
        ).scalar_one_or_none()
        if topic is None:
            raise ValueError("Topic not found for source.")
        query = (
            select(KnowledgeUnitModel)
            .where(
                KnowledgeUnitModel.source_id == source_id,
                KnowledgeUnitModel.topic_id == topic_id,
            )
            .order_by(KnowledgeUnitModel.position, KnowledgeUnitModel.id)
        )
    else:
        if topic_id is not None:
            raise ValueError("SELECTION scope does not accept topic_id.")
        if not knowledge_unit_ids:
            raise ValueError("SELECTION scope requires knowledge_unit_ids.")
        if len(set(knowledge_unit_ids)) != len(knowledge_unit_ids):
            raise ValueError("knowledge_unit_ids must not contain duplicates.")
        query = (
            select(KnowledgeUnitModel)
            .where(
                KnowledgeUnitModel.source_id == source_id,
                KnowledgeUnitModel.id.in_(knowledge_unit_ids),
            )
            .order_by(KnowledgeUnitModel.position, KnowledgeUnitModel.id)
        )

    units = (await session.execute(query)).scalars().all()
    if scope == ProductionScope.SELECTION and len(units) != len(knowledge_unit_ids):
        raise ValueError("One or more selected knowledge units do not belong to source.")
    if not units:
        raise ValueError("Production scope contains no knowledge units.")
    return list(units)


async def create_production_job(
    session: AsyncSession,
    source_id: UUID,
    scope: ProductionScope,
    topic_id: UUID | None = None,
    knowledge_unit_ids: list[UUID] | None = None,
) -> ProductionJobModel:
    units = await _resolve_units(
        session,
        source_id,
        scope,
        topic_id,
        knowledge_unit_ids or [],
    )
    job = ProductionJobModel(
        id=uuid4(),
        source_id=source_id,
        scope=scope.value,
        status=ProductionJobStatus.QUEUED.value,
        total_items=len(units),
    )
    session.add(job)
    for position, unit in enumerate(units, start=1):
        session.add(
            ProductionJobItemModel(
                id=uuid4(),
                job_id=job.id,
                knowledge_unit_id=unit.id,
                position=position,
                status=ProductionJobItemStatus.PENDING.value,
            )
        )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise
    await session.refresh(job)
    logger.info(
        "event=PRODUCTION_JOB_CREATED job_id=%s source_id=%s scope=%s total=%s",
        job.id,
        source_id,
        scope.value,
        len(units),
    )
    return job


async def _claim_job(job_id: UUID) -> bool:
    async with SessionFactory() as session:
        result = await session.execute(
            update(ProductionJobModel)
            .where(
                ProductionJobModel.id == job_id,
                ProductionJobModel.status == ProductionJobStatus.QUEUED.value,
            )
            .values(
                status=ProductionJobStatus.RUNNING.value,
                attempts=ProductionJobModel.attempts + 1,
                started_at=func.coalesce(ProductionJobModel.started_at, func.now()),
                updated_at=func.now(),
                error_code=None,
                error_message=None,
            )
        )
        await session.commit()
        return result.rowcount == 1


async def _claim_next_item(job_id: UUID) -> UUID | None:
    async with SessionFactory() as session:
        item = (
            await session.execute(
                select(ProductionJobItemModel)
                .where(
                    ProductionJobItemModel.job_id == job_id,
                    ProductionJobItemModel.status == ProductionJobItemStatus.PENDING.value,
                )
                .order_by(ProductionJobItemModel.position)
                .limit(1)
            )
        ).scalar_one_or_none()
        if item is None:
            return None

        result = await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.id == item.id,
                ProductionJobItemModel.status == ProductionJobItemStatus.PENDING.value,
            )
            .values(
                status=ProductionJobItemStatus.RUNNING.value,
                attempts=ProductionJobItemModel.attempts + 1,
                updated_at=func.now(),
                error_code=None,
                error_message=None,
            )
        )
        await session.commit()
        if result.rowcount != 1:
            return None
        return item.id


async def _recover_stale(job_id: UUID) -> None:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=_stale_seconds())
    async with SessionFactory() as session:
        await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.job_id == job_id,
                ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
                ProductionJobItemModel.updated_at < threshold,
            )
            .values(
                status=ProductionJobItemStatus.PENDING.value,
                error_code="PRODUCTION_RECOVERED_AFTER_PROCESS_STALE",
                error_message="Recovered after the previous process stopped before completion.",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.execute(
            update(ProductionJobModel)
            .where(
                ProductionJobModel.id == job_id,
                ProductionJobModel.status == ProductionJobStatus.RUNNING.value,
                ProductionJobModel.updated_at < threshold,
            )
            .values(
                status=ProductionJobStatus.QUEUED.value,
                current_item_id=None,
                error_code="PRODUCTION_RECOVERED_AFTER_PROCESS_STALE",
                error_message="Recovered after the previous process stopped before completion.",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _update_progress(job_id: UUID, current_item_id: UUID | None = None) -> tuple[int, int, int, int]:
    async with SessionFactory() as session:
        completed = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.COMPLETED.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        failed = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.FAILED.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        pending = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.PENDING.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        running = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        await session.execute(
            update(ProductionJobModel)
            .where(ProductionJobModel.id == job_id)
            .values(
                completed_items=completed,
                failed_items=failed,
                current_item_id=current_item_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        return completed, failed, pending, running


async def _complete_item(job_id: UUID, item_id: UUID, post_id: UUID) -> None:
    async with SessionFactory() as session:
        await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.id == item_id,
                ProductionJobItemModel.job_id == job_id,
                ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
            )
            .values(
                status=ProductionJobItemStatus.COMPLETED.value,
                post_id=post_id,
                error_code=None,
                error_message=None,
                completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _fail_item(job_id: UUID, item_id: UUID, exc: Exception) -> None:
    code = getattr(exc, "code", None) or "PRODUCTION_ERROR"
    async with SessionFactory() as session:
        await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.id == item_id,
                ProductionJobItemModel.job_id == job_id,
                ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
            )
            .values(
                status=ProductionJobItemStatus.FAILED.value,
                error_code=code,
                error_message=str(exc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _finalize(job_id: UUID) -> None:
    async with SessionFactory() as session:
        pending = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status.in_(
                            [ProductionJobItemStatus.PENDING.value, ProductionJobItemStatus.RUNNING.value]
                        ),
                    )
                )
            ).scalar_one()
            or 0
        )
        failed = int(
            (
                await session.execute(
                    select(func.count(ProductionJobItemModel.id)).where(
                        ProductionJobItemModel.job_id == job_id,
                        ProductionJobItemModel.status == ProductionJobItemStatus.FAILED.value,
                    )
                )
            ).scalar_one()
            or 0
        )
        if pending:
            return
        status = (
            ProductionJobStatus.FAILED.value
            if failed
            else ProductionJobStatus.COMPLETED.value
        )
        await session.execute(
            update(ProductionJobModel)
            .where(ProductionJobModel.id == job_id)
            .values(
                status=status,
                current_item_id=None,
                completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                error_code="PRODUCTION_ITEMS_FAILED" if failed else None,
                error_message=(
                    f"{failed} production item(s) failed."
                    if failed
                    else None
                ),
            )
        )
        await session.commit()


class ProductionJobRunner:
    """Durable sequential runner; each material delegates to ProducePost."""

    def __init__(self, drafter, resolver: ControlPlaneResolver) -> None:
        self.producer = ProducePost(drafter, resolver)

    async def run(self, job_id: UUID) -> None:
        await _recover_stale(job_id)
        if not await _claim_job(job_id):
            return

        try:
            while True:
                item_id = await _claim_next_item(job_id)
                if item_id is None:
                    break

                async with SessionFactory() as session:
                    item = (
                        await session.execute(
                            select(ProductionJobItemModel).where(
                                ProductionJobItemModel.id == item_id,
                                ProductionJobItemModel.job_id == job_id,
                            )
                        )
                    ).scalar_one()
                    await session.execute(
                        update(ProductionJobModel)
                        .where(ProductionJobModel.id == job_id)
                        .values(
                            current_item_id=item.id,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                    knowledge_unit_id = item.knowledge_unit_id

                try:
                    async with SessionFactory() as session:
                        post = await self.producer.execute(session, knowledge_unit_id)
                        artifact = post_to_artifact(post)
                    await _complete_item(job_id, item_id, artifact.id)
                    await _update_progress(job_id, None)
                except Exception as exc:
                    logger.exception(
                        "event=PRODUCTION_ITEM_FAILED job_id=%s item_id=%s",
                        job_id,
                        item_id,
                    )
                    await _fail_item(job_id, item_id, exc)
                    await _update_progress(job_id, None)
                    continue

            await _finalize(job_id)
        except Exception as exc:
            logger.exception("event=PRODUCTION_JOB_FAILED job_id=%s", job_id)
            async with SessionFactory() as session:
                await session.execute(
                    update(ProductionJobModel)
                    .where(ProductionJobModel.id == job_id)
                    .values(
                        status=ProductionJobStatus.FAILED.value,
                        error_code="PRODUCTION_RUNNER_ERROR",
                        error_message=str(exc),
                        current_item_id=None,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()


async def resume_production_job(
    session: AsyncSession,
    job_id: UUID,
    retry_failed: bool = False,
) -> ProductionJobModel:
    job = (
        await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == job_id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise ValueError("Production job not found.")
    if job.status == ProductionJobStatus.RUNNING.value:
        raise ValueError("Production job is already running.")
    if job.status == ProductionJobStatus.COMPLETED.value:
        return job

    await session.execute(
        update(ProductionJobItemModel)
        .where(
            ProductionJobItemModel.job_id == job_id,
            ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
        )
        .values(
            status=ProductionJobItemStatus.PENDING.value,
            error_code="PRODUCTION_RESUMED_STALE_ITEM",
            error_message="Reset to pending during explicit resume.",
            updated_at=datetime.now(timezone.utc),
        )
    )
    if retry_failed:
        await session.execute(
            update(ProductionJobItemModel)
            .where(
                ProductionJobItemModel.job_id == job_id,
                ProductionJobItemModel.status == ProductionJobItemStatus.FAILED.value,
            )
            .values(
                status=ProductionJobItemStatus.PENDING.value,
                error_code=None,
                error_message=None,
                completed_at=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
    job.status = ProductionJobStatus.QUEUED.value
    job.current_item_id = None
    job.error_code = None
    job.error_message = None
    job.completed_at = None
    job.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(job)
    return job


async def recover_stale_production_jobs() -> list[UUID]:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=_stale_seconds())
    recovered: list[UUID] = []
    async with SessionFactory() as session:
        stale = (
            await session.execute(
                select(ProductionJobModel).where(
                    ProductionJobModel.status == ProductionJobStatus.RUNNING.value,
                    ProductionJobModel.updated_at < threshold,
                )
            )
        ).scalars().all()
        for job in stale:
            await session.execute(
                update(ProductionJobItemModel)
                .where(
                    ProductionJobItemModel.job_id == job.id,
                    ProductionJobItemModel.status == ProductionJobItemStatus.RUNNING.value,
                )
                .values(
                    status=ProductionJobItemStatus.PENDING.value,
                    error_code="PRODUCTION_RECOVERED_AFTER_PROCESS_STALE",
                    error_message="Recovered after the previous process stopped before completion.",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            job.status = ProductionJobStatus.QUEUED.value
            job.current_item_id = None
            job.error_code = "PRODUCTION_RECOVERED_AFTER_PROCESS_STALE"
            job.error_message = "Recovered after the previous process stopped before completion."
            job.updated_at = datetime.now(timezone.utc)
            recovered.append(job.id)

        queued = (
            await session.execute(
                select(ProductionJobModel).where(
                    ProductionJobModel.status == ProductionJobStatus.QUEUED.value
                )
            )
        ).scalars().all()
        for job in queued:
            if job.id not in recovered:
                recovered.append(job.id)
        await session.commit()
    return recovered


async def run_production_job(job_id: UUID) -> None:
    await ProductionJobRunner(GeminiEditorialDrafter(), ControlPlaneResolver()).run(job_id)
