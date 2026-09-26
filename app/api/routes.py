import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.discovery_jobs import (
    DiscoveryJobStage,
    DiscoveryJobStatus,
    create_discovery_job,
    retry_discovery_job,
    run_discovery_job,
)
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.api.console import NASHR_CONSOLE_HTML
from app.infrastructure.database.models import DiscoveryJobModel, KnowledgeUnitModel, SourceModel, TopicModel
from app.infrastructure.database.session import get_session
from app.infrastructure.storage import LocalFileStorage

router = APIRouter()


class PublishTelegramRequest(BaseModel):
    content: str = Field(min_length=1)


def get_ingest_pdf() -> IngestPdf:
    return IngestPdf(LocalFileStorage(os.getenv("STORAGE_PATH", "./storage")))


def get_create_telegram_draft() -> CreateTelegramDraft:
    from app.adapters.drafting.gemini import GeminiEditorialDrafter
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
        "materials_discovered": job.materials_discovered,
        "current_topic_id": str(job.current_topic_id) if job.current_topic_id else None,
        "error": job.error_message,
        "retryable": job.retryable,
        "attempts": job.attempts,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def _topic_payload(topic: TopicModel, units: list[KnowledgeUnitModel]) -> dict[str, Any]:
    return {
        "id": str(topic.id),
        "position": topic.position,
        "title": topic.title,
        "description": topic.description,
        "source_reference": topic.source_reference,
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
    result = await session.execute(select(SourceModel).order_by(SourceModel.created_at.desc()))
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
    return _job_payload(job)


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
    result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
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
