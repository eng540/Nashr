"""Owner-only private preparation, never Google connection or upload."""

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.instagram_connections import owner, mutation_owner, HEADERS
from app.infrastructure.database.session import get_session
from app.application import youtube_plan_review as service

router = APIRouter(
    prefix="/api/connections/youtube/materials", tags=["youtube-private-review"]
)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_id: str | None = Field(default=None, pattern=r"^UC[A-Za-z0-9_-]{22}$")
    privacy: str | None = Field(default=None, pattern=r"^(private|unlisted|public)$")
    made_for_kids: StrictBool | None = None
    contains_synthetic_media: StrictBool | None = None
    rights_confirmed: StrictBool | None = None
    category_id: str | None = Field(default=None, pattern=r"^[0-9]{1,10}$")
    planned_at: datetime | None = None
    timezone_name: str | None = Field(default=None, max_length=100)


class Save(Review):
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.post("/{uid}/preview")
async def preview(
    uid: UUID,
    payload: Review,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    mutation_owner(request)
    try:
        result = await service.preview(session, uid, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return JSONResponse(result, headers=HEADERS)


@router.post("/{uid}/drafts")
async def save(
    uid: UUID,
    payload: Save,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    mutation_owner(request)
    try:
        result = await service.save_draft(session, uid, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return JSONResponse(result, headers=HEADERS)


@router.get("/{uid}/drafts")
async def history(
    uid: UUID, request: Request, session: AsyncSession = Depends(get_session)
):
    owner(request)
    try:
        result = await service.list_drafts(session, uid)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return JSONResponse(result, headers=HEADERS)


@router.post("/{uid}/drafts/{draft_id}/cancel")
async def cancel(
    uid: UUID,
    draft_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    mutation_owner(request)
    try:
        result = await service.cancel_draft(session, uid, draft_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return JSONResponse(result, headers=HEADERS)
