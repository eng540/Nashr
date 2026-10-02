from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.posts import PostStatus
from app.infrastructure.database.models import PostModel, ScheduleItemModel


async def _load_post(session: AsyncSession, post_id: UUID) -> PostModel:
    post = (await session.execute(
        select(PostModel).where(PostModel.id == post_id)
    )).scalar_one_or_none()
    if post is None:
        raise LookupError("Post not found.")
    return post


async def _ensure_not_processing(session: AsyncSession, post_id: UUID) -> None:
    result = await session.execute(
        select(ScheduleItemModel.id).where(
            ScheduleItemModel.post_id == post_id,
            ScheduleItemModel.status == "PROCESSING",
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise RuntimeError("Post cannot change editorial state while publication execution is in progress.")


class ReviewPost:
    """Apply the durable human editorial decision to the canonical Post."""

    async def approve(
        self,
        session: AsyncSession,
        post_id: UUID,
        note: str | None = None,
    ) -> PostModel:
        post = await _load_post(session, post_id)
        if post.status == PostStatus.APPROVED.value:
            raise RuntimeError("Post is already APPROVED.")
        if post.status not in (PostStatus.DRAFT.value, PostStatus.REJECTED.value):
            raise RuntimeError(f"Cannot approve Post from {post.status}.")
        await _ensure_not_processing(session, post_id)
        post.status = PostStatus.APPROVED.value
        post.reviewed_at = datetime.now(timezone.utc)
        post.review_note = note.strip() if note and note.strip() else None
        await session.commit()
        await session.refresh(post)
        return post

    async def edit(
        self,
        session: AsyncSession,
        post_id: UUID,
        content: str,
    ) -> PostModel:
        content = content.strip()
        if not content:
            raise ValueError("Post content cannot be empty.")
        post = await _load_post(session, post_id)
        await _ensure_not_processing(session, post_id)
        post.content = content
        post.status = PostStatus.DRAFT.value
        post.reviewed_at = None
        post.review_note = None
        await session.execute(
            update(ScheduleItemModel)
            .where(
                ScheduleItemModel.post_id == post.id,
                ScheduleItemModel.status == "PENDING",
            )
            .values(
                status="CANCELLED",
                last_error="Post content changed; editorial approval is required again.",
                processing_started_at=None,
            )
        )
        await session.commit()
        await session.refresh(post)
        return post

    async def reject(
        self,
        session: AsyncSession,
        post_id: UUID,
        reason: str,
    ) -> PostModel:
        reason = reason.strip()
        if not reason:
            raise ValueError("Rejection reason is required.")
        post = await _load_post(session, post_id)
        if post.status != PostStatus.DRAFT.value:
            raise RuntimeError(f"Cannot reject Post from {post.status}.")
        await _ensure_not_processing(session, post_id)
        post.status = PostStatus.REJECTED.value
        post.reviewed_at = datetime.now(timezone.utc)
        post.review_note = reason
        await session.commit()
        await session.refresh(post)
        return post


async def bulk_approve(
    session: AsyncSession,
    post_ids: list[UUID],
    note: str | None = None,
) -> dict[str, object]:
    """Approve multiple Posts server-side while isolating per-Post validation failures."""
    unique_ids = list(dict.fromkeys(post_ids))
    if not unique_ids:
        raise ValueError("At least one Post is required.")
    if len(unique_ids) > 500:
        raise ValueError("At most 500 Posts can be approved at once.")

    posts = {
        post.id: post
        for post in (
            await session.execute(
                select(PostModel).where(PostModel.id.in_(unique_ids)).with_for_update()
            )
        ).scalars().all()
    }
    processing_ids = {
        post_id
        for post_id in (
            await session.execute(
                select(ScheduleItemModel.post_id)
                .where(
                    ScheduleItemModel.post_id.in_(unique_ids),
                    ScheduleItemModel.status == "PROCESSING",
                )
            )
        ).scalars().all()
    }

    approved: list[PostModel] = []
    results: list[dict[str, object]] = []
    for post_id in unique_ids:
        post = posts.get(post_id)
        if post is None:
            results.append({
                "post_id": str(post_id),
                "status": "FAILED",
                "reason_code": "POST_NOT_FOUND",
                "message": "Post not found.",
            })
            continue
        if post.status == PostStatus.APPROVED.value:
            results.append({
                "post_id": str(post_id),
                "status": "FAILED",
                "reason_code": "ALREADY_APPROVED",
                "message": "Post is already APPROVED.",
            })
            continue
        if post.status not in (PostStatus.DRAFT.value, PostStatus.REJECTED.value):
            results.append({
                "post_id": str(post_id),
                "status": "FAILED",
                "reason_code": "INVALID_STATUS",
                "message": f"Cannot approve Post from {post.status}.",
            })
            continue
        if post_id in processing_ids:
            results.append({
                "post_id": str(post_id),
                "status": "FAILED",
                "reason_code": "PROCESSING",
                "message": "Post cannot change editorial state while publication execution is in progress.",
            })
            continue

        post.status = PostStatus.APPROVED.value
        post.reviewed_at = datetime.now(timezone.utc)
        post.review_note = note.strip() if note and note.strip() else None
        approved.append(post)
        results.append({
            "post_id": str(post_id),
            "status": "APPROVED",
            "reason_code": None,
            "message": "Post approved.",
        })

    await session.commit()
    for post in approved:
        await session.refresh(post)

    return {
        "approved_count": len(approved),
        "failed_count": len(results) - len(approved),
        "results": results,
    }
