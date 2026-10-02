import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from app.adapters.publishing.telegram import TelegramPublisher
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.domain.scheduling import ScheduleItemStatus, ScheduleStatus
from app.infrastructure.database.models import (
    KnowledgeUnitModel,
    PostModel,
    PublicationModel,
    ScheduleItemModel,
    ScheduleModel,
    SourceModel,
    TopicModel,
)
from app.infrastructure.database.session import SessionFactory


STALE_PROCESSING_AFTER = timedelta(minutes=10)


def validate_timezone(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Timezone is required.")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Invalid timezone.") from exc
    return value


def validate_scheduled_at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduled_at must be timezone-aware.")
    return value.astimezone(timezone.utc)


def build_schedule_times(
    post_ids: list[UUID],
    start_at: datetime,
    interval_minutes: int,
    timezone_name: str,
) -> list[tuple[UUID, datetime]]:
    """Build deterministic publication times from a local schedule start and interval."""
    if not post_ids:
        raise ValueError("At least one Post is required.")
    if len(post_ids) != len(set(post_ids)):
        raise ValueError("A Post cannot appear more than once in a Schedule.")
    if interval_minutes < 1 or interval_minutes > 7 * 24 * 60:
        raise ValueError("interval_minutes must be between 1 and 10080.")
    timezone_name = validate_timezone(timezone_name)
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        raise ValueError("start_at must be timezone-aware.")
    local_start = start_at.astimezone(ZoneInfo(timezone_name))
    return [
        (
            post_id,
            validate_scheduled_at(
                (local_start + timedelta(minutes=index * interval_minutes)).astimezone(
                    timezone.utc
                )
            ),
        )
        for index, post_id in enumerate(post_ids)
    ]


async def get_posts_publish_eligibility(
    session: AsyncSession,
    post_ids: list[UUID],
) -> dict[str, object]:
    """Return per-Post publish eligibility using the existing Post/Publication/Schedule state."""
    unique_ids = list(dict.fromkeys(post_ids))
    if not unique_ids:
        return {"eligible_ids": [], "blocked": []}

    posts = (
        await session.execute(
            select(PostModel)
            .options(selectinload(PostModel.publications))
            .where(PostModel.id.in_(unique_ids))
        )
    ).scalars().all()
    by_id = {post.id: post for post in posts}

    scheduled_rows = (
        await session.execute(
            select(ScheduleItemModel.post_id, ScheduleItemModel.status, ScheduleModel.status)
            .join(ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id)
            .where(
                ScheduleItemModel.post_id.in_(unique_ids),
                or_(
                    ScheduleModel.status.in_(
                        (
                            ScheduleStatus.DRAFT.value,
                            ScheduleStatus.ACTIVE.value,
                            ScheduleStatus.PAUSED.value,
                        )
                    ),
                    (
                        (ScheduleModel.status == ScheduleStatus.COMPLETED.value)
                        & ScheduleItemModel.status.in_(
                            (
                                ScheduleItemStatus.PENDING.value,
                                ScheduleItemStatus.PROCESSING.value,
                                ScheduleItemStatus.FAILED.value,
                            )
                        )
                    ),
                ),
            )
        )
    ).all()
    scheduled_by_post: dict[UUID, list[tuple[str, str]]] = {}
    for post_id, item_status, schedule_status in scheduled_rows:
        scheduled_by_post.setdefault(post_id, []).append((item_status, schedule_status))

    eligible_ids: list[UUID] = []
    blocked: list[dict[str, object]] = []
    for post_id in unique_ids:
        post = by_id.get(post_id)
        if post is None:
            blocked.append({"post_id": str(post_id), "reason_code": "POST_NOT_FOUND", "message": "Post not found."})
            continue
        if post.status != "APPROVED":
            blocked.append({"post_id": str(post_id), "reason_code": "POST_NOT_APPROVED", "message": "Post is not APPROVED."})
            continue
        if not post.content.strip():
            blocked.append({"post_id": str(post_id), "reason_code": "EMPTY_CONTENT", "message": "Post content is empty."})
            continue
        if any(publication.status == "PUBLISHED" for publication in post.publications):
            blocked.append({"post_id": str(post_id), "reason_code": "ALREADY_PUBLISHED", "message": "Post was already published."})
            continue
        existing = scheduled_by_post.get(post_id, [])
        if existing:
            item_status, schedule_status = existing[0]
            blocked.append({
                "post_id": str(post_id),
                "reason_code": "ALREADY_SCHEDULED",
                "message": f"Post already exists in a {schedule_status} schedule ({item_status}).",
            })
            continue
        eligible_ids.append(post_id)

    return {"eligible_ids": eligible_ids, "blocked": blocked}


async def create_schedule(
    session: AsyncSession,
    name: str,
    timezone_name: str,
    items: list[tuple[UUID, datetime]],
    idempotency_key: str | None = None,
) -> ScheduleModel:
    name = name.strip()
    if not name:
        raise ValueError("Schedule name cannot be empty.")
    if len(name) > 300:
        raise ValueError("Schedule name is too long.")
    if idempotency_key is not None and not idempotency_key.strip():
        raise ValueError("Idempotency key cannot be empty.")
    if idempotency_key is not None and len(idempotency_key) > 100:
        raise ValueError("Idempotency key is too long.")
    timezone_name = validate_timezone(timezone_name)
    if not items:
        raise ValueError("Schedule must contain at least one item.")
    post_ids = [post_id for post_id, _ in items]
    if len(post_ids) != len(set(post_ids)):
        raise ValueError("A Post cannot appear more than once in a Schedule.")
    normalized = [(post_id, validate_scheduled_at(when)) for post_id, when in items]
    # Serialize schedule creation for the selected Posts so two concurrent plans
    # cannot both pass eligibility and reserve the same Post.
    locked_result = await session.execute(
        select(PostModel.id)
        .where(PostModel.id.in_(post_ids))
        .with_for_update()
    )
    found = set(locked_result.scalars().all())
    missing = [post_id for post_id in post_ids if post_id not in found]
    if missing:
        raise LookupError("Post not found.")
    eligibility = await get_posts_publish_eligibility(session, post_ids)
    blocked = eligibility["blocked"]
    if blocked:
        details = "؛ ".join(
            f"{entry['post_id']}: {entry['message']}" for entry in blocked[:8]
        )
        raise RuntimeError("Some Posts are not eligible for scheduling: " + details)
    schedule = ScheduleModel(id=uuid4(), name=name, timezone=timezone_name, status=ScheduleStatus.DRAFT.value, idempotency_key=idempotency_key.strip() if idempotency_key else None)
    schedule.items = [
        ScheduleItemModel(
            id=uuid4(),
            post_id=post_id,
            position=position,
            scheduled_at=scheduled_at,
            status=ScheduleItemStatus.PENDING.value,
        )
        for position, (post_id, scheduled_at) in enumerate(normalized, start=1)
    ]
    session.add(schedule)
    await session.commit()
    await session.refresh(schedule)
    return schedule


async def get_schedule(session: AsyncSession, schedule_id: UUID) -> ScheduleModel | None:
    result = await session.execute(
        select(ScheduleModel)
        .options(
            selectinload(ScheduleModel.items)
            .selectinload(ScheduleItemModel.post)
            .selectinload(PostModel.knowledge_unit)
            .selectinload(KnowledgeUnitModel.topic)
            .selectinload(TopicModel.source)
            .defer(SourceModel.file_payload),
            selectinload(ScheduleModel.items)
            .selectinload(ScheduleItemModel.post)
            .selectinload(PostModel.knowledge_unit)
            .selectinload(KnowledgeUnitModel.source)
            .defer(SourceModel.file_payload),
            selectinload(ScheduleModel.items).selectinload(ScheduleItemModel.publication),
            selectinload(ScheduleModel.items).selectinload(ScheduleItemModel.post).selectinload(PostModel.publications),
        )
        .where(ScheduleModel.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if schedule is not None:
        schedule.items.sort(key=lambda item: item.position)
    return schedule


def schedule_counts(schedule: ScheduleModel) -> dict[str, int]:
    counts = {key: 0 for key in ("total_items", "pending_items", "published_items", "failed_items", "skipped_items", "cancelled_items")}
    counts["total_items"] = len(schedule.items)
    for item in schedule.items:
        if item.status == ScheduleItemStatus.PENDING.value:
            counts["pending_items"] += 1
        elif item.status == ScheduleItemStatus.PUBLISHED.value:
            counts["published_items"] += 1
        elif item.status == ScheduleItemStatus.FAILED.value:
            counts["failed_items"] += 1
        elif item.status == ScheduleItemStatus.SKIPPED.value:
            counts["skipped_items"] += 1
        elif item.status == ScheduleItemStatus.CANCELLED.value:
            counts["cancelled_items"] += 1
    return counts


async def list_schedule_rows(session: AsyncSession, limit: int, offset: int) -> tuple[list[ScheduleModel], int]:
    total = int((await session.execute(select(func.count(ScheduleModel.id)))).scalar_one() or 0)
    result = await session.execute(
        select(ScheduleModel)
        .options(selectinload(ScheduleModel.items))
        .order_by(ScheduleModel.created_at.desc(), ScheduleModel.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all(), total


def next_scheduled_at(schedule: ScheduleModel) -> datetime | None:
    values = [
        item.scheduled_at
        for item in schedule.items
        if item.status == ScheduleItemStatus.PENDING.value
    ]
    return min(values) if values else None


async def validate_schedule_for_activation(session: AsyncSession, schedule_id: UUID) -> dict[str, object]:
    """Validate schedule-level invariants while reporting item-level blockers without stopping siblings."""
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise LookupError("Schedule not found.")

    errors: list[str] = []
    warnings: list[str] = []
    blocked_items: list[dict[str, object]] = []
    items = sorted(schedule.items, key=lambda item: item.position)

    if not items:
        errors.append("الخطة لا تحتوي على أي منشور.")

    seen: set[UUID] = set()
    for item in items:
        if item.post_id in seen:
            errors.append(f"المنشور في الموضع {item.position} مكرر داخل الخطة.")
        seen.add(item.post_id)

        if item.status == ScheduleItemStatus.FAILED.value:
            blocked_items.append({
                "item_id": str(item.id),
                "post_id": str(item.post_id),
                "position": item.position,
                "reason_code": "PREVIOUS_FAILURE",
                "message": f"المنشور «{item.post.knowledge_unit.title}» لديه فشل سابق؛ سيبقى معزولًا عن بقية العناصر.",
            })
            continue
        if item.status in (
            ScheduleItemStatus.CANCELLED.value,
            ScheduleItemStatus.SKIPPED.value,
            ScheduleItemStatus.PUBLISHED.value,
        ):
            continue
        if item.status != ScheduleItemStatus.PENDING.value:
            blocked_items.append({
                "item_id": str(item.id),
                "post_id": str(item.post_id),
                "position": item.position,
                "reason_code": "INVALID_ITEM_STATE",
                "message": f"المنشور «{item.post.knowledge_unit.title}» في حالة تنفيذ غير قابلة للتنفيذ الآن: {item.status}.",
            })
            continue

        post = item.post
        if post.status != "APPROVED":
            blocked_items.append({
                "item_id": str(item.id),
                "post_id": str(item.post_id),
                "position": item.position,
                "reason_code": "POST_NOT_APPROVED",
                "message": f"المنشور «{item.post.knowledge_unit.title}» غير معتمد حاليًا؛ لن يمنع بقية الخطة.",
            })
        if not post.content.strip():
            blocked_items.append({
                "item_id": str(item.id),
                "post_id": str(item.post_id),
                "position": item.position,
                "reason_code": "EMPTY_CONTENT",
                "message": f"المنشور «{item.post.knowledge_unit.title}» لا يحتوي على محتوى قابل للنشر؛ لن يمنع بقية الخطة.",
            })
        if item.scheduled_at.tzinfo is None or item.scheduled_at.utcoffset() is None:
            blocked_items.append({
                "item_id": str(item.id),
                "post_id": str(item.post_id),
                "position": item.position,
                "reason_code": "INVALID_TIME",
                "message": f"وقت نشر «{item.post.knowledge_unit.title}» غير صالح؛ لن يمنع بقية الخطة.",
            })
        if any(publication.status == "PUBLISHED" for publication in item.post.publications):
            blocked_items.append({
                "item_id": str(item.id),
                "post_id": str(item.post_id),
                "position": item.position,
                "reason_code": "ALREADY_PUBLISHED",
                "message": f"المنشور «{item.post.knowledge_unit.title}» سبق نشره؛ سيتم تجاوزه ولن يعاد نشره.",
            })

    try:
        validate_timezone(schedule.timezone)
    except ValueError as exc:
        errors.append(str(exc))

    if schedule.status == ScheduleStatus.PAUSED.value:
        warnings.append("الخطة متوقفة مؤقتًا؛ ستستأنف التنفيذ بعد التفعيل.")
    if blocked_items:
        warnings.append(f"توجد {len(blocked_items)} عناصر غير قابلة للتنفيذ حاليًا؛ ستُعالج كل منها دون إيقاف بقية الخطة.")
    if any(item.status == ScheduleItemStatus.PUBLISHED.value for item in items):
        warnings.append("توجد منشورات منشورة بالفعل داخل الخطة؛ لن يعاد نشرها.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "blocked_items": blocked_items,
        "total_items": len(items),
        "pending_items": sum(item.status == ScheduleItemStatus.PENDING.value for item in items),
        "published_items": sum(item.status == ScheduleItemStatus.PUBLISHED.value for item in items),
        "failed_items": sum(item.status == ScheduleItemStatus.FAILED.value for item in items),
        "skipped_items": sum(item.status == ScheduleItemStatus.SKIPPED.value for item in items),
        "processable_pending_items": sum(
            item.status == ScheduleItemStatus.PENDING.value
            and item.post.status == "APPROVED"
            and bool(item.post.content.strip())
            and item.scheduled_at.tzinfo is not None
            and not any(publication.status == "PUBLISHED" for publication in item.post.publications)
            for item in items
        ),
    }


def transition(schedule: ScheduleModel, action: str, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    allowed = {
        "activate": {ScheduleStatus.DRAFT.value, ScheduleStatus.PAUSED.value},
        "pause": {ScheduleStatus.ACTIVE.value},
        "cancel": {ScheduleStatus.DRAFT.value, ScheduleStatus.ACTIVE.value, ScheduleStatus.PAUSED.value},
    }
    if schedule.status not in allowed[action]:
        raise RuntimeError(f"Cannot {action} schedule from {schedule.status}.")
    if action == "activate":
        schedule.status = ScheduleStatus.ACTIVE.value
        schedule.started_at = schedule.started_at or now
        schedule.completed_at = None
    elif action == "pause":
        schedule.status = ScheduleStatus.PAUSED.value
    else:
        schedule.status = ScheduleStatus.CANCELLED.value
        for item in schedule.items:
            if item.status in (ScheduleItemStatus.PENDING.value, ScheduleItemStatus.FAILED.value):
                item.status = ScheduleItemStatus.CANCELLED.value


async def update_schedule_item_time(
    session: AsyncSession, schedule_id: UUID, item_id: UUID, scheduled_at: datetime
) -> ScheduleItemModel:
    item = (await session.execute(
        select(ScheduleItemModel).where(
            ScheduleItemModel.id == item_id,
            ScheduleItemModel.schedule_id == schedule_id,
        )
    )).scalar_one_or_none()
    if item is None:
        raise LookupError("Schedule item not found.")
    if item.status != ScheduleItemStatus.PENDING.value:
        raise RuntimeError("Only PENDING schedule items can be rescheduled.")
    item.scheduled_at = validate_scheduled_at(scheduled_at)
    await session.commit()
    return item


async def retry_failed_items(session: AsyncSession, schedule_id: UUID) -> int:
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise LookupError("Schedule not found.")
    if schedule.status not in (
        ScheduleStatus.ACTIVE.value,
        ScheduleStatus.PAUSED.value,
        ScheduleStatus.COMPLETED.value,
    ):
        raise RuntimeError("Failed items can only be retried in ACTIVE, PAUSED, or COMPLETED schedules.")
    count = 0
    for item in schedule.items:
        if item.status == ScheduleItemStatus.FAILED.value:
            item.status = ScheduleItemStatus.PENDING.value
            item.last_error = None
            item.processing_started_at = None
            count += 1
    if count and schedule.status == ScheduleStatus.COMPLETED.value:
        schedule.status = ScheduleStatus.ACTIVE.value
        schedule.completed_at = None
    await session.commit()
    return count


async def retry_failed_item(
    session: AsyncSession,
    schedule_id: UUID,
    item_id: UUID,
) -> ScheduleItemModel:
    schedule = await get_schedule(session, schedule_id)
    if schedule is None:
        raise LookupError("Schedule not found.")
    if schedule.status not in (
        ScheduleStatus.ACTIVE.value,
        ScheduleStatus.PAUSED.value,
        ScheduleStatus.COMPLETED.value,
    ):
        raise RuntimeError("A failed item can only be retried in ACTIVE, PAUSED, or COMPLETED schedules.")
    item = next((candidate for candidate in schedule.items if candidate.id == item_id), None)
    if item is None:
        raise LookupError("Schedule item not found.")
    if item.status != ScheduleItemStatus.FAILED.value:
        raise RuntimeError("Only FAILED schedule items can be retried individually.")
    item.status = ScheduleItemStatus.PENDING.value
    item.last_error = None
    item.processing_started_at = None
    if schedule.status == ScheduleStatus.COMPLETED.value:
        schedule.status = ScheduleStatus.ACTIVE.value
        schedule.completed_at = None
    await session.commit()
    return item


async def recover_stale_schedule_items(now: datetime | None = None) -> list[UUID]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - STALE_PROCESSING_AFTER
    async with SessionFactory() as session:
        result = await session.execute(
            select(ScheduleItemModel.id, ScheduleModel.status)
            .join(ScheduleModel)
            .where(
                ScheduleItemModel.status == ScheduleItemStatus.PROCESSING.value,
                ScheduleItemModel.processing_started_at.is_not(None),
                ScheduleItemModel.processing_started_at < cutoff,
                ScheduleModel.status.in_(
                    (
                        ScheduleStatus.ACTIVE.value,
                        ScheduleStatus.PAUSED.value,
                        ScheduleStatus.CANCELLED.value,
                    )
                ),
            )
        )
        rows = result.all()
        ids = [item_id for item_id, _ in rows]
        for item_id, schedule_status in rows:
            target_status = (
                ScheduleItemStatus.CANCELLED.value
                if schedule_status == ScheduleStatus.CANCELLED.value
                else ScheduleItemStatus.PENDING.value
            )
            await session.execute(
                update(ScheduleItemModel)
                .where(
                    ScheduleItemModel.id == item_id,
                    ScheduleItemModel.status == ScheduleItemStatus.PROCESSING.value,
                )
                .values(
                    status=target_status,
                    processing_started_at=None,
                    last_error=(
                        "Recovered stale PROCESSING item from CANCELLED schedule; "
                        "external publication outcome is unknown."
                        if target_status == ScheduleItemStatus.CANCELLED.value
                        else None
                    ),
                )
            )
        if ids:
            await session.commit()
        return ids


async def _claim_due_item(now: datetime) -> UUID | None:
    async with SessionFactory() as session:
        result = await session.execute(
            select(ScheduleItemModel)
            .join(ScheduleModel)
            .where(
                ScheduleModel.status == ScheduleStatus.ACTIVE.value,
                ScheduleItemModel.status == ScheduleItemStatus.PENDING.value,
                ScheduleItemModel.scheduled_at <= now,
            )
            .order_by(ScheduleItemModel.scheduled_at, ScheduleItemModel.position, ScheduleItemModel.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        item.status = ScheduleItemStatus.PROCESSING.value
        item.attempts += 1
        item.processing_started_at = now
        item.last_error = None
        await session.commit()
        return item.id


async def _finish_schedule_if_complete(session: AsyncSession, schedule_id: UUID) -> None:
    schedule = (await session.execute(
        select(ScheduleModel).where(ScheduleModel.id == schedule_id)
    )).scalar_one()
    statuses = list((await session.execute(
        select(ScheduleItemModel.status).where(ScheduleItemModel.schedule_id == schedule_id)
    )).scalars().all())
    if (
        schedule.status == ScheduleStatus.ACTIVE.value
        and statuses
        and all(
            status in (
                ScheduleItemStatus.PUBLISHED.value,
                ScheduleItemStatus.SKIPPED.value,
                ScheduleItemStatus.FAILED.value,
                ScheduleItemStatus.CANCELLED.value,
            )
            for status in statuses
        )
    ):
        schedule.status = ScheduleStatus.COMPLETED.value
        schedule.completed_at = datetime.now(timezone.utc)


async def _execute_claimed_item(
    item_id: UUID,
    publisher=None,
    destination: str | None = None,
) -> None:
    destination = destination or os.getenv("TELEGRAM_DESTINATION_ID", "")
    if not destination:
        async with SessionFactory() as session:
            item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.id == item_id))).scalar_one_or_none()
            if item:
                item.status = ScheduleItemStatus.FAILED.value
                item.last_error = "TELEGRAM_DESTINATION_ID is required."
                item.processing_started_at = None
                await session.commit()
                await _finish_schedule_if_complete(session, item.schedule_id)
                await session.commit()
        return

    async with SessionFactory() as session:
        item = (await session.execute(
            select(ScheduleItemModel)
            .options(selectinload(ScheduleItemModel.post).selectinload(PostModel.knowledge_unit))
            .where(ScheduleItemModel.id == item_id)
        )).scalar_one_or_none()
        if item is None:
            return
        post = item.post
        # Re-check the canonical editorial gate immediately before any publication work.
        if post.status != "APPROVED":
            item.status = ScheduleItemStatus.CANCELLED.value
            item.last_error = "Post is no longer APPROVED; editorial approval is required before publication."
            item.processing_started_at = None
            await session.commit()
            await _finish_schedule_if_complete(session, item.schedule_id)
            await session.commit()
            return
        existing = (await session.execute(
            select(PublicationModel)
            .where(
                PublicationModel.post_id == post.id,
                PublicationModel.platform == "telegram",
                PublicationModel.destination == destination,
            )
            .order_by(PublicationModel.created_at.asc(), PublicationModel.id.asc())
            .limit(1)
        )).scalar_one_or_none()

        if existing is not None and existing.status == "PUBLISHED":
            item.status = ScheduleItemStatus.SKIPPED.value
            item.publication_id = existing.id
            item.published_at = existing.published_at
            item.processing_started_at = None
            await session.commit()
            await _finish_schedule_if_complete(session, item.schedule_id)
            await session.commit()
            return

        if existing is not None and existing.status in ("READY", "PUBLISHING"):
            item.status = ScheduleItemStatus.FAILED.value
            item.last_error = "Publication is already in progress; automatic retry is unsafe."
            item.publication_id = existing.id
            item.processing_started_at = None
            await session.commit()
            await _finish_schedule_if_complete(session, item.schedule_id)
            await session.commit()
            return

        if existing is not None and existing.status == "FAILED":
            existing.status = "DRAFT"
            existing.error_message = None
            await session.commit()
            publication_id = existing.id
        elif existing is not None:
            publication_id = existing.id
        else:
            draft = await CreateTelegramDraft.execute_for_post(session, post, destination)
            publication_id = draft.id

    # All DB work above is committed before the external Telegram call.
    publisher = publisher or TelegramPublisher()
    async with SessionFactory() as session:
        try:
            publication = await ApproveAndPublish(publisher).execute(session, publication_id)
        except Exception as exc:
            result = await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.id == item_id))
            item = result.scalar_one_or_none()
            if item:
                item.status = ScheduleItemStatus.FAILED.value
                item.last_error = str(exc)
                item.publication_id = publication_id
                item.processing_started_at = None
                await session.commit()
                await _finish_schedule_if_complete(session, item.schedule_id)
                await session.commit()
            return
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.id == item_id))).scalar_one_or_none()
        if item is None:
            return
        item.publication_id = publication.id
        item.processing_started_at = None
        if publication.status.value == "PUBLISHED":
            item.status = ScheduleItemStatus.PUBLISHED.value
            item.published_at = publication.published_at
            item.last_error = None
        else:
            item.status = ScheduleItemStatus.FAILED.value
            item.last_error = publication.error_message or "Publication failed."
        await session.commit()
        await _finish_schedule_if_complete(session, item.schedule_id)
        await session.commit()


async def process_due_schedule_items(
    limit: int = 20,
    publisher=None,
    destination: str | None = None,
    now: datetime | None = None,
) -> int:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100.")
    now = now or datetime.now(timezone.utc)
    await recover_stale_schedule_items(now)
    processed = 0
    while processed < limit:
        item_id = await _claim_due_item(now)
        if item_id is None:
            break
        try:
            await _execute_claimed_item(item_id, publisher=publisher, destination=destination)
        except Exception as exc:
            # Never let one unexpected item-level exception stop the due batch.
            async with SessionFactory() as session:
                item = (
                    await session.execute(
                        select(ScheduleItemModel).where(ScheduleItemModel.id == item_id)
                    )
                ).scalar_one_or_none()
                if item is not None and item.status == ScheduleItemStatus.PROCESSING.value:
                    item.status = ScheduleItemStatus.FAILED.value
                    item.last_error = str(exc)
                    item.processing_started_at = None
                    await session.commit()
                    await _finish_schedule_if_complete(session, item.schedule_id)
                    await session.commit()
        processed += 1
    return processed
