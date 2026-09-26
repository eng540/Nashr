import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.adapters.extraction.gemini import GeminiBookMapper, GeminiTopicMaterialDiscoverer
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.discover_book import DiscoverBook
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.api.console import NASHR_CONSOLE_HTML
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel, TopicModel
from app.infrastructure.database.session import get_session
from app.infrastructure.storage import LocalFileStorage

router = APIRouter()


class PublishTelegramRequest(BaseModel):
    content: str = Field(min_length=1)


def get_ingest_pdf() -> IngestPdf:
    return IngestPdf(LocalFileStorage(os.getenv("STORAGE_PATH", "./storage")))


def get_discover_book() -> DiscoverBook:
    return DiscoverBook(GeminiBookMapper(), GeminiTopicMaterialDiscoverer())


def get_create_telegram_draft() -> CreateTelegramDraft:
    return CreateTelegramDraft(GeminiEditorialDrafter())


def get_approve_and_publish() -> ApproveAndPublish:
    return ApproveAndPublish(TelegramPublisher())


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/console", response_class=HTMLResponse, include_in_schema=False)
async def console() -> HTMLResponse:
    return HTMLResponse(content=NASHR_CONSOLE_HTML)


@router.post("/sources")
async def create_source(file: UploadFile = File(...), session: AsyncSession = Depends(get_session), use_case: IngestPdf = Depends(get_ingest_pdf)) -> dict[str, Any]:
    try:
        source = await use_case.execute(session, file.filename or "upload.pdf", file.content_type or "", await file.read())
        return {"id": str(source.id), "status": source.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _topic_payload(topic: TopicModel, units: list[KnowledgeUnitModel]) -> dict[str, Any]:
    return {
        "id": str(topic.id), "position": topic.position, "title": topic.title,
        "description": topic.description, "source_reference": topic.source_reference,
        "materials": [{
            "id": str(unit.id), "position": unit.position, "title": unit.title, "kind": unit.kind,
            "content": unit.content, "original_text": unit.original_text, "source_reference": unit.source_reference,
        } for unit in sorted(units, key=lambda item: item.position)],
    }


@router.post("/sources/{source_id}/extract")
async def extract_source(source_id: UUID, session: AsyncSession = Depends(get_session), use_case: DiscoverBook = Depends(get_discover_book)) -> dict[str, Any]:
    try:
        book_map, units = await use_case.execute(session, source_id)
        grouped: dict[UUID, list[KnowledgeUnitModel]] = {topic.id: [] for topic in book_map.topics}
        if units:
            result = await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id))
            for unit in result.scalars().all():
                if unit.topic_id in grouped:
                    grouped[unit.topic_id].append(unit)
        topics = [{
            "id": str(topic.id), "position": topic.position, "title": topic.title,
            "description": topic.description, "source_reference": topic.source_reference,
            "materials": [{
                "id": str(unit.id), "position": unit.position, "title": unit.title, "kind": unit.kind,
                "content": unit.content, "original_text": unit.original_text, "source_reference": unit.source_reference,
            } for unit in grouped[topic.id]],
        } for topic in book_map.topics]
        return {
            "source_id": str(source_id), "book": {"title": book_map.title, "description": book_map.description},
            "topics": topics,
            "knowledge_unit_ids": [str(unit.id) for unit in units],
            "knowledge_units": [{"id": str(unit.id), "position": unit.position, "title": unit.title, "content": unit.content, "original_text": unit.original_text, "source_reference": unit.source_reference, "topic_id": str(unit.topic_id) if unit.topic_id else None, "kind": unit.kind} for unit in units],
            "count": len(units),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sources/{source_id}/book-map")
async def get_book_map(source_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    result = await session.execute(select(SourceModel).where(SourceModel.id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    topics_result = await session.execute(select(TopicModel).where(TopicModel.source_id == source_id).order_by(TopicModel.position))
    topics = topics_result.scalars().all()
    units_result = await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id).order_by(KnowledgeUnitModel.position))
    units = units_result.scalars().all()
    grouped = {topic.id: [] for topic in topics}
    for unit in units:
        if unit.topic_id in grouped:
            grouped[unit.topic_id].append(unit)
    return {"source_id": str(source_id), "book": {"title": source.book_title or source.filename, "description": source.book_description or ""}, "topics": [_topic_payload(topic, grouped[topic.id]) for topic in topics], "count": len(units)}


@router.post("/knowledge-units/{knowledge_unit_id}/draft")
async def create_telegram_draft(knowledge_unit_id: UUID, session: AsyncSession = Depends(get_session), use_case: CreateTelegramDraft = Depends(get_create_telegram_draft)) -> dict[str, Any]:
    destination = os.getenv("TELEGRAM_DESTINATION_ID", "")
    if not destination:
        raise HTTPException(status_code=500, detail="TELEGRAM_DESTINATION_ID is required.")
    try:
        publication = await use_case.execute(session, knowledge_unit_id, destination)
        return {"id": str(publication.id), "knowledge_unit_id": str(publication.knowledge_unit_id), "platform": publication.platform, "destination": publication.destination, "status": publication.status.value, "content": publication.content}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/publications/{publication_id}/publish")
async def publish_telegram(publication_id: UUID, payload: PublishTelegramRequest, session: AsyncSession = Depends(get_session), use_case: ApproveAndPublish = Depends(get_approve_and_publish)) -> dict[str, Any]:
    try:
        publication = await use_case.execute(session, publication_id, payload.content)
        return {"id": str(publication.id), "status": publication.status.value, "external_id": publication.external_id, "error_message": publication.error_message, "published_at": publication.published_at}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
