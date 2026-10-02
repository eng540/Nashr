import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.posts import ProducePost
from app.application.reviews import ReviewPost, bulk_approve
from app.application.production_jobs import create_production_job, resume_production_job, run_production_job
from app.application.scheduling import (
    build_schedule_times, create_schedule, get_schedule, list_schedule_rows, next_scheduled_at,
    process_due_schedule_items, retry_failed_items, transition, update_schedule_item_time,
    validate_timezone, validate_schedule_for_activation, get_posts_publish_eligibility,
    retry_failed_item,
)
from app.domain.production_jobs import ProductionScope
from app.infrastructure.database.models import (
    ProductionJobItemModel,
    ProductionJobModel,
    ScheduleItemModel,
    ScheduleModel,
    PublicationModel,
)
from app.application.discovery_jobs import (
    DiscoveryJobStatus,
    create_discovery_job,
    retry_discovery_job,
    run_discovery_job,
)
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.api.console import NASHR_CONSOLE_HTML
from app.api.post_console import NASHR_POSTS_HTML
from app.infrastructure.database.models import BookMapSectionModel, DiscoveryJobModel, KnowledgeUnitModel, PostModel, SourceModel, TopicModel
from app.infrastructure.database.session import get_session
from app.infrastructure.storage import LocalFileStorage

router = APIRouter()


class ProductionJobRequest(BaseModel):
    source_id: UUID
    scope: ProductionScope
    topic_id: UUID | None = None
    knowledge_unit_ids: list[UUID] = Field(default_factory=list)


class ProductionJobResumeRequest(BaseModel):
    retry_failed: bool = False


class PostUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)


class PostApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5_000)


class BulkPostApproveRequest(BaseModel):
    post_ids: list[UUID] = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=5_000)


class PostRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=5_000)

class ScheduleItemRequest(BaseModel):
    post_id: UUID
    scheduled_at: datetime


class ScheduleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    timezone: str = Field(min_length=1, max_length=100)
    items: list[ScheduleItemRequest] | None = Field(default=None, max_length=500)
    post_ids: list[UUID] | None = Field(default=None, max_length=500)
    start_at: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=10080)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=100)


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)


class ScheduleItemUpdateRequest(BaseModel):
    scheduled_at: datetime




def _post_payload(post: PostModel) -> dict[str, Any]:
    unit = post.knowledge_unit
    topic = unit.topic
    source = topic.source if topic is not None else unit.source
    published = any(publication.status == "PUBLISHED" for publication in post.publications)
    return {
        "post_id": str(post.id),
        "title": unit.title,
        "status": post.status,
        "knowledge_unit_id": str(unit.id),
        "topic_id": str(topic.id) if topic is not None else None,
        "topic_title": topic.title if topic is not None else None,
        "source_id": str(source.id),
        "source_title": source.book_title or source.filename,
        "content": post.content,
        "content_preview": post.content[:300],
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "reviewed_at": post.reviewed_at,
        "review_note": post.review_note,
        "published": published,
    }


def _post_query_options():
    return (
        selectinload(PostModel.knowledge_unit)
        .selectinload(KnowledgeUnitModel.topic)
        .selectinload(TopicModel.source)
        .defer(SourceModel.file_payload),
        selectinload(PostModel.knowledge_unit)
        .selectinload(KnowledgeUnitModel.source)
        .defer(SourceModel.file_payload),
        selectinload(PostModel.publications),
    )



class PublishTelegramRequest(BaseModel):
    content: str = Field(min_length=1)


def get_ingest_pdf() -> IngestPdf:
    return IngestPdf(LocalFileStorage(os.getenv("STORAGE_PATH", "./storage")))


def get_create_telegram_draft() -> CreateTelegramDraft:
    return CreateTelegramDraft(GeminiEditorialDrafter())


def get_approve_and_publish() -> ApproveAndPublish:
    return ApproveAndPublish(TelegramPublisher())


def _job_payload(job: DiscoveryJobModel) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "source_id": str(job.source_id),
        "status": job.status,
        "stage": job.stage,
        "topics_total": job.topics_total,
        "topics_completed": job.topics_completed,
        "chunks_total": job.chunks_total,
        "chunks_completed": job.chunks_completed,
        "materials_discovered": job.materials_discovered,
        "current_topic_id": str(job.current_topic_id) if job.current_topic_id else None,
        "current_chunk_id": str(job.current_chunk_id) if job.current_chunk_id else None,
        "error_code": job.error_code,
        "error": job.error_message,
        "retryable": job.retryable,
        "attempts": job.attempts,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def _production_job_payload(job: ProductionJobModel, pending_items: int | None = None) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "source_id": str(job.source_id),
        "status": job.status,
        "scope": job.scope,
        "total_items": job.total_items,
        "completed_items": job.completed_items,
        "failed_items": job.failed_items,
        "pending_items": pending_items if pending_items is not None else max(job.total_items - job.completed_items - job.failed_items, 0),
        "current_item_id": str(job.current_item_id) if job.current_item_id else None,
        "attempts": job.attempts,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


async def _load_production_job_payload(session: AsyncSession, job: ProductionJobModel) -> dict[str, Any]:
    pending = int(
        (await session.execute(
            select(func.count(ProductionJobItemModel.id)).where(
                ProductionJobItemModel.job_id == job.id,
                ProductionJobItemModel.status == "PENDING",
            )
        )).scalar_one() or 0
    )
    return _production_job_payload(job, pending_items=pending)


def _book_map_checkpoint_payload(sections: list[BookMapSectionModel]) -> dict[str, Any]:
    return {
        "total": len(sections),
        "completed": sum(section.status == "COMPLETED" for section in sections),
        "running": sum(section.status == "RUNNING" for section in sections),
        "failed": sum(section.status == "FAILED" for section in sections),
        "current": next(
            (
                {
                    "section_index": section.section_index,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "status": section.status,
                    "error_code": section.error_code,
                }
                for section in sections
                if section.status == "RUNNING"
            ),
            None,
        ),
    }


def _topic_payload(topic: TopicModel, units: list[KnowledgeUnitModel]) -> dict[str, Any]:
    return {
        "id": str(topic.id),
        "position": topic.position,
        "title": topic.title,
        "description": topic.description,
        "source_reference": topic.source_reference,
        "page_start": topic.page_start,
        "page_end": topic.page_end,
        "discovery_status": topic.discovery_status,
        "discovery_error": topic.discovery_error,
        "materials": [
            {
                "id": str(unit.id),
                "position": unit.position,
                "title": unit.title,
                "kind": unit.kind,
                "content": unit.content,
                "original_text": unit.original_text,
                "source_reference": unit.source_reference,
                "discovery_page_start": unit.discovery_page_start,
                "discovery_page_end": unit.discovery_page_end,
                "discovery_chunk_index": unit.discovery_chunk_index,
            }
            for unit in sorted(units, key=lambda item: item.position)
        ],
    }


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/console", response_class=HTMLResponse, include_in_schema=False)
async def console() -> HTMLResponse:
    return HTMLResponse(content=NASHR_CONSOLE_HTML)


@router.post("/sources")
async def create_source(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    use_case: IngestPdf = Depends(get_ingest_pdf),
) -> dict[str, Any]:
    try:
        source = await use_case.execute(
            session,
            file.filename or "upload.pdf",
            file.content_type or "",
            await file.read(),
        )
        return {"id": str(source.id), "status": source.status.value, "filename": source.filename}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sources")
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    result = await session.execute(
        select(SourceModel).options(defer(SourceModel.file_payload)).order_by(SourceModel.created_at.desc())
    )
    return [
        {
            "id": str(source.id),
            "filename": source.filename,
            "status": source.status,
            "book_title": source.book_title or source.filename,
            "created_at": source.created_at,
        }
        for source in result.scalars().all()
    ]


@router.post("/sources/{source_id}/discovery", status_code=status.HTTP_202_ACCEPTED)
async def start_discovery(
    source_id: UUID,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        job = await create_discovery_job(session, source_id)
        if job.status == DiscoveryJobStatus.QUEUED:
            background_tasks.add_task(run_discovery_job, job.id)
        return _job_payload(job)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sources/{source_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract_source_compat(
    source_id: UUID,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compatibility adapter for the former blocking extraction endpoint."""
    return await start_discovery(source_id, background_tasks, session)


@router.get("/sources/{source_id}/discovery/status")
async def discovery_status(source_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    source_result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
    if source_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    result = await session.execute(
        select(DiscoveryJobModel)
        .where(DiscoveryJobModel.source_id == source_id)
        .order_by(DiscoveryJobModel.created_at.desc())
    )
    job = result.scalars().first()
    if job is None:
        return {"source_id": str(source_id), "status": "NOT_STARTED"}

    sections_result = await session.execute(
        select(BookMapSectionModel)
        .where(BookMapSectionModel.source_id == source_id)
        .order_by(BookMapSectionModel.section_index)
    )
    return {
        **_job_payload(job),
        "book_map_checkpoints": _book_map_checkpoint_payload(sections_result.scalars().all()),
    }


@router.post("/sources/{source_id}/discovery/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_discovery(
    source_id: UUID,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        job = await retry_discovery_job(session, source_id)
        background_tasks.add_task(run_discovery_job, job.id)
        return _job_payload(job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sources/{source_id}/book-map")
async def get_book_map(source_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    result = await session.execute(
        select(SourceModel).options(defer(SourceModel.file_payload)).where(SourceModel.id == source_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")

    topics_result = await session.execute(
        select(TopicModel).where(TopicModel.source_id == source_id).order_by(TopicModel.position)
    )
    topics = topics_result.scalars().all()
    units_result = await session.execute(
        select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id).order_by(KnowledgeUnitModel.position)
    )
    units = units_result.scalars().all()
    grouped = {topic.id: [] for topic in topics}
    for unit in units:
        if unit.topic_id in grouped:
            grouped[unit.topic_id].append(unit)

    job_result = await session.execute(
        select(DiscoveryJobModel)
        .where(DiscoveryJobModel.source_id == source_id)
        .order_by(DiscoveryJobModel.created_at.desc())
    )
    job = job_result.scalars().first()
    return {
        "source_id": str(source_id),
        "book": {"title": source.book_title or source.filename, "description": source.book_description or ""},
        "topics": [_topic_payload(topic, grouped[topic.id]) for topic in topics],
        "count": len(units),
        "job": _job_payload(job) if job else None,
    }


def get_produce_post() -> ProducePost:
    return ProducePost(GeminiEditorialDrafter())


@router.post("/knowledge-units/{knowledge_unit_id}/post")
async def produce_post(
    knowledge_unit_id: UUID,
    session: AsyncSession = Depends(get_session),
    use_case: ProducePost = Depends(get_produce_post),
) -> dict[str, Any]:
    try:
        post = await use_case.execute(session, knowledge_unit_id)
        return {"post_id": str(post.id), "status": post.status.value}
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if "not found" in detail.lower() else 400, detail=detail) from exc


@router.post("/production-jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_production_job_route(
    payload: ProductionJobRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        job = await create_production_job(
            session,
            payload.source_id,
            payload.scope,
            payload.topic_id,
            payload.knowledge_unit_ids,
        )
        background_tasks.add_task(run_production_job, job.id)
        return await _load_production_job_payload(session, job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/production-jobs/{job_id}")
async def production_job_status(job_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = (await session.execute(
        select(ProductionJobModel).where(ProductionJobModel.id == job_id)
    )).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Production job not found.")
    return await _load_production_job_payload(session, job)


@router.post("/production-jobs/{job_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_production_job_route(
    job_id: UUID,
    payload: ProductionJobResumeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        job = await resume_production_job(session, job_id, payload.retry_failed)
        if job.status == "QUEUED":
            background_tasks.add_task(run_production_job, job.id)
        return await _load_production_job_payload(session, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



def _schedule_item_payload(item: ScheduleItemModel) -> dict[str, Any]:
    post = item.post
    unit = post.knowledge_unit
    topic = unit.topic
    source = topic.source if topic is not None else unit.source
    publication = item.publication
    return {
        "id": str(item.id),
        "position": item.position,
        "post_id": str(post.id),
        "title": unit.title,
        "status": item.status,
        "scheduled_at": item.scheduled_at,
        "attempts": item.attempts,
        "publication_id": str(item.publication_id) if item.publication_id else None,
        "published_at": item.published_at,
        "last_error": item.last_error,
        "published": bool(publication and publication.status == "PUBLISHED"),
        "content_preview": post.content[:300],
        "knowledge_unit_id": str(unit.id),
        "topic_id": str(topic.id) if topic is not None else None,
        "topic_title": topic.title if topic is not None else None,
        "source_id": str(source.id),
        "source_title": source.book_title or source.filename,
    }


def _schedule_payload(schedule: ScheduleModel, detail: bool = False) -> dict[str, Any]:
    items = sorted(schedule.items, key=lambda x: x.position)
    payload = {
        "id": str(schedule.id),
        "name": schedule.name,
        "status": schedule.status,
        "timezone": schedule.timezone,
        "total_items": len(items),
        "pending_items": sum(i.status == "PENDING" for i in items),
        "published_items": sum(i.status == "PUBLISHED" for i in items),
        "failed_items": sum(i.status == "FAILED" for i in items),
        "next_scheduled_at": next_scheduled_at(schedule),
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
        "started_at": schedule.started_at,
        "completed_at": schedule.completed_at,
    }
    if detail:
        payload["items"] = [_schedule_item_payload(item) for item in items]
    return payload


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule_route(
    payload: ScheduleCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        if payload.items is not None:
            if not payload.items:
                raise ValueError("Schedule must contain at least one item.")
            if payload.post_ids is not None or payload.start_at is not None or payload.interval_minutes is not None:
                raise ValueError("Use either explicit items or post_ids with start_at and interval_minutes.")
            items = [(item.post_id, item.scheduled_at) for item in payload.items]
        else:
            if not payload.post_ids or payload.start_at is None or payload.interval_minutes is None:
                raise ValueError("post_ids, start_at, and interval_minutes are required.")
            items = build_schedule_times(
                payload.post_ids,
                payload.start_at,
                payload.interval_minutes,
                payload.timezone,
            )

        if payload.idempotency_key:
            existing = (
                await session.execute(
                    select(ScheduleModel).where(
                        ScheduleModel.idempotency_key == payload.idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                loaded = await get_schedule(session, existing.id)
                if loaded is None:
                    raise RuntimeError("Idempotent Schedule no longer exists.")
                existing_items = sorted(loaded.items, key=lambda item: item.position)
                same_request = (
                    loaded.name == payload.name.strip()
                    and loaded.timezone == validate_timezone(payload.timezone)
                    and len(existing_items) == len(items)
                    and all(
                        item.post_id == post_id
                        and item.scheduled_at == scheduled_at
                        for item, (post_id, scheduled_at) in zip(existing_items, items)
                    )
                )
                if not same_request:
                    raise RuntimeError("Idempotency key is already associated with a different Schedule request.")
                return _schedule_payload(loaded, detail=True)

        try:
            schedule = await create_schedule(
                session,
                payload.name,
                payload.timezone,
                items,
                payload.idempotency_key,
            )
        except IntegrityError:
            await session.rollback()
            if not payload.idempotency_key:
                raise
            existing = (
                await session.execute(
                    select(ScheduleModel).where(
                        ScheduleModel.idempotency_key == payload.idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                raise
            loaded = await get_schedule(session, existing.id)
            if loaded is None:
                raise
            existing_items = sorted(loaded.items, key=lambda item: item.position)
            if not (
                loaded.name == payload.name.strip()
                and loaded.timezone == validate_timezone(payload.timezone)
                and len(existing_items) == len(items)
                and all(
                    item.post_id == post_id
                    and item.scheduled_at == scheduled_at
                    for item, (post_id, scheduled_at) in zip(existing_items, items)
                )
            ):
                raise RuntimeError("Idempotency key is already associated with a different Schedule request.")
            return _schedule_payload(loaded, detail=True)
        return _schedule_payload(await get_schedule(session, schedule.id), detail=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _upcoming_item_payload(item: ScheduleItemModel) -> dict[str, Any]:
    post = item.post
    unit = post.knowledge_unit
    return {
        "schedule_id": str(item.schedule_id),
        "schedule_name": item.schedule.name,
        "timezone": item.schedule.timezone,
        "item_id": str(item.id),
        "post_id": str(item.post_id),
        "title": unit.title,
        "scheduled_at": item.scheduled_at,
        "status": item.status,
        "position": item.position,
        "attempts": item.attempts,
        "last_error": item.last_error,
    }


@router.get("/schedules/calendar")
async def schedule_calendar(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    timezone_name: str = Query(default="UTC", alias="timezone"),
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        tz = ZoneInfo(validate_timezone(timezone_name))
        local_date = datetime.strptime(date, "%Y-%m-%d").date()
        start_local = datetime.combine(local_date, datetime.min.time(), tzinfo=tz)
        end_local = start_local + timedelta(days=1)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(status_code=400, detail="Invalid date or timezone.") from exc

    result = await session.execute(
        select(ScheduleItemModel)
        .join(ScheduleModel)
        .options(
            selectinload(ScheduleItemModel.schedule),
            selectinload(ScheduleItemModel.post).selectinload(PostModel.knowledge_unit),
        )
        .where(
            ScheduleItemModel.scheduled_at >= start_local.astimezone(timezone.utc),
            ScheduleItemModel.scheduled_at < end_local.astimezone(timezone.utc),
            ScheduleItemModel.status.in_(
                ("PENDING", "PROCESSING", "PUBLISHED", "FAILED", "SKIPPED", "CANCELLED")
            ),
        )
        .order_by(ScheduleItemModel.scheduled_at, ScheduleItemModel.position, ScheduleItemModel.id)
        .limit(limit)
    )
    return {
        "date": date,
        "timezone": timezone_name,
        "items": [_upcoming_item_payload(item) for item in result.scalars().all()],
    }


@router.get("/schedules/upcoming")
async def upcoming_schedule_items(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the durable upcoming publishing queue from active schedules."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    result = await session.execute(
        select(ScheduleItemModel)
        .join(ScheduleModel)
        .options(
            selectinload(ScheduleItemModel.schedule),
            selectinload(ScheduleItemModel.post).selectinload(PostModel.knowledge_unit),
        )
        .where(
            ScheduleModel.status == "ACTIVE",
            ScheduleItemModel.status == "PENDING",
            ScheduleItemModel.scheduled_at >= now,
            ScheduleItemModel.scheduled_at <= horizon,
        )
        .order_by(
            ScheduleItemModel.scheduled_at,
            ScheduleItemModel.position,
            ScheduleItemModel.id,
        )
        .limit(limit)
    )
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": str(item.id),
                "schedule_id": str(item.schedule_id),
                "schedule_name": item.schedule.name,
                "post_id": str(item.post_id),
                "title": item.post.knowledge_unit.title,
                "content_preview": item.post.content[:300],
                "scheduled_at": item.scheduled_at,
                "timezone": item.schedule.timezone,
                "position": item.position,
                "status": item.status,
            }
            for item in items
        ],
        "days": days,
        "limit": limit,
    }


@router.get("/schedules")
async def list_schedules(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    rows, total = await list_schedule_rows(session, limit, offset)
    return {"items": [_schedule_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/schedules/eligibility")
async def schedule_eligibility(
    post_ids: list[UUID] = Query(..., min_length=1, max_length=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await get_posts_publish_eligibility(session, post_ids)


@router.get("/schedules/{schedule_id}")
async def schedule_detail(schedule_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return _schedule_payload(schedule, detail=True)


@router.patch("/schedules/{schedule_id}")
async def update_schedule_route(schedule_id: UUID, payload: ScheduleUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    if schedule.status in ("COMPLETED", "CANCELLED"):
        raise HTTPException(status_code=409, detail="Schedule cannot be edited in its current state.")
    if payload.name is not None:
        schedule.name = payload.name.strip()
    if payload.timezone is not None:
        try:
            schedule.timezone = validate_timezone(payload.timezone)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return _schedule_payload(await get_schedule(session, schedule.id), detail=True)


@router.patch("/schedules/{schedule_id}/items/{item_id}")
async def update_schedule_item_route(schedule_id: UUID, item_id: UUID, payload: ScheduleItemUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        await update_schedule_item_time(session, schedule_id, item_id, payload.scheduled_at)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _schedule_payload(await get_schedule(session, schedule_id), detail=True)


@router.get("/schedules/{schedule_id}/validation")
async def schedule_validation_route(schedule_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await validate_schedule_for_activation(session, schedule_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/schedules/{schedule_id}/activate")
async def activate_schedule_route(schedule_id: UUID, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    validation = await validate_schedule_for_activation(session, schedule_id)
    if not validation["valid"]:
        raise HTTPException(status_code=409, detail="لا يمكن تفعيل الخطة: " + "؛ ".join(validation["errors"][:6]))
    try:
        transition(schedule, "activate")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    background_tasks.add_task(process_due_schedule_items)
    return _schedule_payload(await get_schedule(session, schedule.id), detail=True)


@router.post("/schedules/{schedule_id}/pause")
async def pause_schedule_route(schedule_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    try:
        transition(schedule, "pause")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _schedule_payload(await get_schedule(session, schedule.id), detail=True)


@router.post("/schedules/{schedule_id}/cancel")
async def cancel_schedule_route(schedule_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    try:
        transition(schedule, "cancel")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _schedule_payload(await get_schedule(session, schedule.id), detail=True)


@router.post("/schedules/{schedule_id}/items/{item_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_failed_schedule_item_route(
    schedule_id: UUID,
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        await retry_failed_item(session, schedule_id, item_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # The existing lifespan scheduler owns execution; retry only changes durable
    # DB state and never performs a hidden side effect inside this request.
    return {"retried_item_id": str(item_id), "schedule": _schedule_payload(await get_schedule(session, schedule_id), detail=True)}


@router.post("/schedules/{schedule_id}/retry-failed", status_code=status.HTTP_202_ACCEPTED)
async def retry_failed_schedule_route(schedule_id: UUID, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        count = await retry_failed_items(session, schedule_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"retried_items": count, "schedule": _schedule_payload(await get_schedule(session, schedule_id), detail=True)}


@router.post("/schedules/process-due", status_code=status.HTTP_202_ACCEPTED)
async def process_due_schedules_route(background_tasks: BackgroundTasks, limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    background_tasks.add_task(process_due_schedule_items, limit=limit)
    return {"status": "QUEUED", "limit": limit}


@router.get("/posts")
async def list_posts(
    source_id: UUID | None = None,
    topic_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status", max_length=30),
    knowledge_unit_id: UUID | None = None,
    kind: str | None = Query(default=None, max_length=200),
    q: str | None = Query(default=None, max_length=500),
    publication_state: str | None = Query(default=None, alias="publication_state", max_length=30),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    filters = []
    if source_id is not None:
        filters.append(KnowledgeUnitModel.source_id == source_id)
    if topic_id is not None:
        filters.append(KnowledgeUnitModel.topic_id == topic_id)
    if knowledge_unit_id is not None:
        filters.append(PostModel.knowledge_unit_id == knowledge_unit_id)
    if status_filter is not None:
        filters.append(PostModel.status == status_filter)
    if kind is not None:
        filters.append(KnowledgeUnitModel.kind == kind)
    published_exists = select(PublicationModel.id).where(
        PublicationModel.post_id == PostModel.id,
        PublicationModel.status == "PUBLISHED",
    ).exists()
    scheduled_exists = select(ScheduleItemModel.id).join(
        ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id
    ).where(
        ScheduleItemModel.post_id == PostModel.id,
        or_(
            ScheduleModel.status.in_(("DRAFT", "ACTIVE", "PAUSED")),
            (
                (ScheduleModel.status == "COMPLETED")
                & ScheduleItemModel.status.in_(("PENDING", "PROCESSING", "FAILED"))
            ),
        ),
    ).exists()

    if publication_state == "PUBLISHED":
        filters.append(published_exists)
    elif publication_state == "UNPUBLISHED":
        filters.append(~published_exists)
    elif publication_state == "SCHEDULED":
        filters.append(scheduled_exists)
    elif publication_state == "ELIGIBLE":
        filters.extend([
            PostModel.status == "APPROVED",
            func.trim(PostModel.content) != "",
            ~published_exists,
            ~scheduled_exists,
        ])
    elif publication_state not in (None, "", "ALL"):
        raise HTTPException(status_code=400, detail="Invalid publication_state.")

    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            PostModel.content.ilike(pattern) | KnowledgeUnitModel.title.ilike(pattern)
        )

    base = select(PostModel).join(PostModel.knowledge_unit).where(*filters)
    total = int((await session.execute(
        select(func.count(PostModel.id)).select_from(PostModel).join(PostModel.knowledge_unit).where(*filters)
    )).scalar_one() or 0)
    result = await session.execute(
        base.options(*_post_query_options())
        .order_by(PostModel.created_at.desc(), PostModel.id.desc())
        .offset(offset)
        .limit(limit)
    )
    posts = result.scalars().all()
    post_ids = [post.id for post in posts]
    scheduled_ids = set()
    if post_ids:
        scheduled_ids = set(
            (
                await session.execute(
                    select(ScheduleItemModel.post_id)
                    .join(ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id)
                    .where(
                        ScheduleItemModel.post_id.in_(post_ids),
                        or_(
                            ScheduleModel.status.in_(("DRAFT", "ACTIVE", "PAUSED")),
                            (
                                (ScheduleModel.status == "COMPLETED")
                                & ScheduleItemModel.status.in_(("PENDING", "PROCESSING", "FAILED"))
                            ),
                        ),
                    )
                )
            ).scalars().all()
        )
    payloads = []
    for post in posts:
        payload = _post_payload(post)
        published = payload["published"]
        scheduled = post.id in scheduled_ids
        payload["scheduled"] = scheduled
        payload["publish_state"] = (
            "PUBLISHED" if published else "SCHEDULED" if scheduled else "ELIGIBLE"
            if post.status == "APPROVED" and bool(post.content.strip())
            else "NOT_READY"
        )
        payload["eligible_for_scheduling"] = (
            post.status == "APPROVED" and not published and not scheduled and bool(post.content.strip())
        )
        payloads.append(payload)
    return {
        "items": payloads,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/posts/workspace", response_class=HTMLResponse, include_in_schema=False)
async def posts_console() -> HTMLResponse:
    return HTMLResponse(content=NASHR_POSTS_HTML)


@router.get("/posts/{post_id}/telegram-preview")
async def telegram_preview(post_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Return the exact canonical payload the existing Telegram publisher will receive."""
    result = await session.execute(
        select(PostModel)
        .options(*_post_query_options())
        .where(PostModel.id == post_id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    return {
        "post_id": str(post.id),
        "platform": "telegram",
        "destination": os.getenv("TELEGRAM_DESTINATION_ID", ""),
        "content": post.content,
        "status": post.status,
        "ready": post.status == "APPROVED",
    }


@router.get("/posts/{post_id}")
async def get_post(post_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    result = await session.execute(
        select(PostModel)
        .options(*_post_query_options())
        .where(PostModel.id == post_id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    payload = _post_payload(post)
    payload["original_text"] = post.knowledge_unit.original_text
    payload["source_reference"] = post.knowledge_unit.source_reference
    payload["discovery_page_start"] = post.knowledge_unit.discovery_page_start
    payload["discovery_page_end"] = post.knowledge_unit.discovery_page_end
    payload["kind"] = post.knowledge_unit.kind
    return payload


@router.patch("/posts/{post_id}")
async def update_post(
    post_id: UUID,
    payload: PostUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Post content cannot be empty.")
    result = await session.execute(
        select(PostModel)
        .options(*_post_query_options())
        .where(PostModel.id == post_id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    try:
        post = await ReviewPost().edit(session, post_id, content)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = await session.execute(
        select(PostModel)
        .options(*_post_query_options())
        .where(PostModel.id == post_id)
    )
    return _post_payload(result.scalar_one())


@router.post("/posts/bulk-approve")
async def bulk_approve_posts(
    payload: BulkPostApproveRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await bulk_approve(session, payload.post_ids, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/posts/{post_id}/approve")
async def approve_post(
    post_id: UUID,
    payload: PostApproveRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        post = await ReviewPost().approve(session, post_id, payload.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = await session.execute(
        select(PostModel).options(*_post_query_options()).where(PostModel.id == post.id)
    )
    return _post_payload(result.scalar_one())


@router.post("/posts/{post_id}/reject")
async def reject_post(
    post_id: UUID,
    payload: PostRejectRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        post = await ReviewPost().reject(session, post_id, payload.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = await session.execute(
        select(PostModel).options(*_post_query_options()).where(PostModel.id == post.id)
    )
    return _post_payload(result.scalar_one())


@router.post("/knowledge-units/{knowledge_unit_id}/draft")
async def create_telegram_draft(
    knowledge_unit_id: UUID,
    session: AsyncSession = Depends(get_session),
    use_case: CreateTelegramDraft = Depends(get_create_telegram_draft),
) -> dict[str, Any]:
    destination = os.getenv("TELEGRAM_DESTINATION_ID", "")
    if not destination:
        raise HTTPException(status_code=500, detail="TELEGRAM_DESTINATION_ID is required.")
    try:
        publication = await use_case.execute(session, knowledge_unit_id, destination)
        return {
            "id": str(publication.id),
            "post_id": str(publication.post_id) if publication.post_id else None,
            "knowledge_unit_id": str(publication.knowledge_unit_id),
            "platform": publication.platform,
            "destination": publication.destination,
            "status": publication.status.value,
            "content": publication.content,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/publications/{publication_id}/publish")
async def publish_telegram(
    publication_id: UUID,
    payload: PublishTelegramRequest,
    session: AsyncSession = Depends(get_session),
    use_case: ApproveAndPublish = Depends(get_approve_and_publish),
) -> dict[str, Any]:
    try:
        publication = await use_case.execute(session, publication_id, payload.content)
        return {
            "id": str(publication.id),
            "status": publication.status.value,
            "external_id": publication.external_id,
            "error_message": publication.error_message,
            "published_at": publication.published_at,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
