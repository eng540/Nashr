from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
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
