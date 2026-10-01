from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.editorial import IEditorialDrafter
from app.domain.posts import Post, PostStatus
from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, ScheduleItemModel
from app.application.editorial_context import slice_pdf_pages_as_bytes


def _to_domain(row: PostModel) -> Post:
    return Post(
        id=row.id,
        knowledge_unit_id=row.knowledge_unit_id,
        content=row.content,
        status=PostStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        reviewed_at=row.reviewed_at,
        review_note=row.review_note,
    )


async def reset_post_to_draft(session: AsyncSession, post: PostModel, content: str) -> None:
    """Persist an editorial edit and invalidate pending schedule entries."""
    processing = await session.execute(
        select(ScheduleItemModel.id).where(
            ScheduleItemModel.post_id == post.id,
            ScheduleItemModel.status == "PROCESSING",
        ).limit(1)
    )
    if processing.scalar_one_or_none() is not None:
        raise RuntimeError("Post cannot be edited while publication execution is in progress.")

    post.content = content
    post.status = PostStatus.DRAFT.value
    post.reviewed_at = None
    post.review_note = None

    await session.execute(
        __import__("sqlalchemy").update(ScheduleItemModel)
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


class ProducePost:
    """Produce and persist one editorial Post from one KnowledgeUnit."""

    def __init__(self, drafter: IEditorialDrafter) -> None:
        self.drafter = drafter

    async def execute(self, session: AsyncSession, knowledge_unit_id: UUID) -> Post:
        existing = await self._find_existing(session, knowledge_unit_id)
        if existing is not None:
            return _to_domain(existing)

        result = await session.execute(
            select(KnowledgeUnitModel)
            .options(selectinload(KnowledgeUnitModel.source))
            .where(KnowledgeUnitModel.id == knowledge_unit_id)
        )
        unit = result.scalar_one_or_none()
        if unit is None:
            raise ValueError("Knowledge unit not found.")

        source = unit.source
        source_name = source.book_title or source.filename if source is not None else "المصدر"
        pdf_slice: bytes | None = None
        if source is not None and unit.discovery_page_start is not None and unit.discovery_page_end is not None:
            try:
                storage_path = source.ensure_file_on_disk()
                pdf_slice = slice_pdf_pages_as_bytes(
                    str(storage_path),
                    unit.discovery_page_start,
                    unit.discovery_page_end,
                    window_size=10,
                )
            except Exception:
                # Preserve the existing text fallback for missing or malformed source PDFs.
                pdf_slice = None

        content = await self.drafter.draft(
            title=unit.title,
            content=unit.content,
            source_name=source_name,
            pdf_slice=pdf_slice,
        )
        content = content.strip()
        if not content:
            raise ValueError("Editorial drafter returned empty content.")

        row = PostModel(
            id=uuid4(),
            knowledge_unit_id=unit.id,
            content=content,
            status=PostStatus.DRAFT.value,
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await self._find_existing(session, knowledge_unit_id)
            if existing is None:
                raise
            return _to_domain(existing)

        await session.refresh(row)
        return _to_domain(row)

    async def _find_existing(self, session: AsyncSession, knowledge_unit_id: UUID) -> PostModel | None:
        result = await session.execute(
            select(PostModel)
            .where(PostModel.knowledge_unit_id == knowledge_unit_id)
            .order_by(PostModel.created_at.asc(), PostModel.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
