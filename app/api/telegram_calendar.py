"""Read-only paginated Telegram calendar views, registered before legacy routes."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import ScheduleModel, ScheduleItemModel, PostModel
from app.application.scheduling import validate_timezone
from app.api.routes import _upcoming_item_payload
router=APIRouter()

@router.get("/schedules/calendar")
async def schedule_calendar(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    timezone_name: str = Query(default="UTC", alias="timezone"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        tz = ZoneInfo(validate_timezone(timezone_name))
        local_date = datetime.strptime(date, "%Y-%m-%d").date()
        start_local = datetime.combine(local_date, datetime.min.time(), tzinfo=tz)
        end_local = start_local + timedelta(days=1)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(status_code=400, detail="Invalid date or timezone.") from exc

    query = (
        select(ScheduleItemModel)
        .join(ScheduleModel)
        .options(
            selectinload(ScheduleItemModel.schedule),
            selectinload(ScheduleItemModel.artifact),
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
    )
    total = await session.scalar(select(func.count()).select_from(query.with_only_columns(ScheduleItemModel.id).order_by(None).subquery()))
    result = await session.execute(query.offset(offset).limit(limit))
    return {
        "date": date,
        "timezone": timezone_name,
        "total": total, "limit": limit, "offset": offset,
        "items": [_upcoming_item_payload(item) for item in result.scalars().all()],
    }


@router.get("/schedules/upcoming")
async def upcoming_schedule_items(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the durable upcoming publishing queue from active schedules."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    query = (
        select(ScheduleItemModel)
        .join(ScheduleModel)
        .options(
            selectinload(ScheduleItemModel.schedule),
            selectinload(ScheduleItemModel.artifact),
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
    )
    total = await session.scalar(select(func.count()).select_from(query.with_only_columns(ScheduleItemModel.id).order_by(None).subquery()))
    result = await session.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()
    payloads = []
    for item in items:
        payload = _upcoming_item_payload(item)
        if item.post is not None and item.post.content:
            content_preview = item.post.content[:300]
        elif item.artifact is not None:
            artifact = item.artifact
            content_preview = str(((artifact.artifact_metadata or {}).get("caption") or artifact.content or ""))[:300]
        else:
            content_preview = ""
        payloads.append({"id": payload["item_id"], "content_preview": content_preview, **payload})
    return {
        "items": payloads,
        "days": days,
        "total": total, "offset": offset,
        "limit": limit,
    }

