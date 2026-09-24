import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTMLResponse, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.extraction.gemini import GeminiExtractor
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.extract_knowledge import ExtractKnowledge
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.api.console import NASHR_CONSOLE_HTML
from app.infrastructure.database.session import get_session
from app.infrastructure.storage import LocalFileStorage


router = APIRouter()


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Report that the HTTP application is alive."""
    return {"status": "ok"}


def get_ingest_pdf() -> IngestPdf:
    """Build the PDF ingestion use case."""
    return IngestPdf(LocalFileStorage(os.getenv("STORAGE_PATH", "./storage")))


def get_extract_knowledge() -> ExtractKnowledge:
    """Build the Gemini knowledge extraction use case."""
    return ExtractKnowledge(GeminiExtractor())


def get_create_telegram_draft() -> CreateTelegramDraft:
    """Build the Telegram draft use case."""
    return CreateTelegramDraft()


def get_approve_and_publish() -> ApproveAndPublish:
    """Build the Telegram publishing use case."""
    return ApproveAndPublish(TelegramPublisher())


@router.get("/console", response_class=HTMLResponse, include_in_schema=False)
async def console() -> HTMLResponse:
    """Render the lightweight Nashr test console."""
    return HTMLResponse(content=NASHR_CONSOLE_HTML)


@router.post("/sources")
async def create_source(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    use_case: IngestPdf = Depends(get_ingest_pdf),
) -> dict[str, Any]:
    """Receive a PDF and register it as a stored source."""
    try:
        source = await use_case.execute(
            session,
            file.filename or "upload.pdf",
            file.content_type or "",
            await file.read(),
        )
        return {"id": str(source.id), "status": source.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sources/{source_id}/extract")
async def extract_source(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
    use_case: ExtractKnowledge = Depends(get_extract_knowledge),
) -> dict[str, Any]:
    """Extract and persist five knowledge units for a source."""
    try:
        units = await use_case.execute(session, source_id)
        return {
            "source_id": str(source_id),
            "knowledge_unit_ids": [str(unit.id) for unit in units],
            "count": len(units),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge-units/{knowledge_unit_id}/draft")
async def create_telegram_draft(
    knowledge_unit_id: UUID,
    session: AsyncSession = Depends(get_session),
    use_case: CreateTelegramDraft = Depends(get_create_telegram_draft),
) -> dict[str, Any]:
    """Create a Telegram publication draft for a knowledge unit."""
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
    session: AsyncSession = Depends(get_session),
    use_case: ApproveAndPublish = Depends(get_approve_and_publish),
) -> dict[str, Any]:
    """Approve and publish a Telegram publication through the real adapter."""
    try:
        publication = await use_case.execute(session, publication_id)
        return {
            "id": str(publication.id),
            "status": publication.status.value,
            "external_id": publication.external_id,
            "error_message": publication.error_message,
            "published_at": publication.published_at,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
