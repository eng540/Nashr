import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.extraction.gemini import GeminiExtractor
from app.application.extract_knowledge import ExtractKnowledge
from app.application.ingest_pdf import IngestPdf
from app.infrastructure.database.session import get_session
from app.infrastructure.storage import LocalFileStorage


router = APIRouter()


def get_ingest_pdf() -> IngestPdf:
    """Build the PDF ingestion use case."""
    return IngestPdf(LocalFileStorage(os.getenv("STORAGE_PATH", "./storage")))


def get_extract_knowledge() -> ExtractKnowledge:
    """Build the Gemini knowledge extraction use case."""
    return ExtractKnowledge(GeminiExtractor())


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
