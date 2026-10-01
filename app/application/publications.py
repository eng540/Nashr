import io
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pypdf import PdfReader, PdfWriter
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.editorial import IEditorialDrafter
from app.domain.publications import IPublisher, Publication, PublicationStatus
from app.application.posts import ProducePost
from app.application.editorial_context import slice_pdf_pages_as_bytes
from app.infrastructure.database.models import PostModel
from app.infrastructure.database.models import KnowledgeUnitModel, PublicationModel


def _to_domain(row: PublicationModel) -> Publication:
    """Convert a publication row to its domain model."""
    return Publication(
        id=row.id,
        knowledge_unit_id=row.knowledge_unit_id,
        post_id=row.post_id,
        platform=row.platform,
        destination=row.destination,
        content=row.content,
        status=PublicationStatus(row.status),
        external_id=row.external_id,
        error_message=row.error_message,
        created_at=row.created_at,
        published_at=row.published_at,
    )


class CreateTelegramDraft:
    """Create the existing Telegram draft flow from the canonical Post."""

    def __init__(self, drafter: IEditorialDrafter) -> None:
        self.drafter = drafter

    async def execute(self, session: AsyncSession, knowledge_unit_id: UUID, destination: str) -> Publication:
        post = await ProducePost(self.drafter).execute(session, knowledge_unit_id)
        existing_result = await session.execute(
            select(PublicationModel)
            .where(
                PublicationModel.post_id == post.id,
                PublicationModel.platform == "telegram",
                PublicationModel.destination == destination,
            )
            .order_by(PublicationModel.created_at.asc(), PublicationModel.id.asc())
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return _to_domain(existing)

        row = PublicationModel(
            id=uuid4(),
            knowledge_unit_id=post.knowledge_unit_id,
            post_id=post.id,
            platform="telegram",
            destination=destination,
            content=post.content,
            status=PublicationStatus.DRAFT.value,
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(
                select(PublicationModel)
                .where(
                    PublicationModel.post_id == post.id,
                    PublicationModel.platform == "telegram",
                    PublicationModel.destination == destination,
                )
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise
            return _to_domain(existing)
        await session.refresh(row)
        return _to_domain(row)

class ApproveAndPublish:
    """Approve a publication and publish it through a platform adapter."""

    def __init__(self, publisher: IPublisher) -> None:
        """Initialize the publisher."""
        self.publisher = publisher

    async def execute(self, session: AsyncSession, publication_id: UUID, content: str | None = None) -> Publication:
        """Persist optional user edits, then publish and record the final content."""
        if content is not None:
            content = content.strip()
            if not content:
                raise ValueError("Publication content cannot be empty.")
            current = await session.execute(
                select(PublicationModel).where(
                    PublicationModel.id == publication_id,
                    PublicationModel.status == PublicationStatus.DRAFT.value,
                )
            )
            current_row = current.scalar_one_or_none()
            if current_row is None:
                raise ValueError("Publication is not a DRAFT.")
            if current_row.post_id is not None:
                post_result = await session.execute(
                    select(PostModel).where(PostModel.id == current_row.post_id)
                )
                post = post_result.scalar_one_or_none()
                if post is not None:
                    post.content = content
            edited = await session.execute(
                update(PublicationModel)
                .where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.DRAFT.value)
                .values(content=content)
            )
            if edited.rowcount != 1:
                raise ValueError("Publication is not a DRAFT.")
            await session.commit()

        claimed = await session.execute(
            update(PublicationModel)
            .where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.DRAFT.value)
            .values(status=PublicationStatus.READY.value)
        )
        if claimed.rowcount != 1:
            raise ValueError("Publication is not a DRAFT.")
        await session.commit()

        claimed = await session.execute(
            update(PublicationModel)
            .where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.READY.value)
            .values(status=PublicationStatus.PUBLISHING.value, error_message=None)
        )
        if claimed.rowcount != 1:
            raise ValueError("Publication is not READY.")
        await session.commit()

        result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
        row = result.scalar_one()
        # The provider call must never hold an open database transaction.
        await session.commit()
        try:
            published = await self.publisher.publish(destination=row.destination, content=row.content)
        except Exception as exc:
            await session.execute(
                update(PublicationModel)
                .where(PublicationModel.id == publication_id)
                .values(status=PublicationStatus.FAILED.value, error_message=str(exc))
            )
            await session.commit()
            result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
            return _to_domain(result.scalar_one())

        await session.execute(
            update(PublicationModel)
            .where(PublicationModel.id == publication_id)
            .values(
                status=PublicationStatus.PUBLISHED.value,
                external_id=published.external_id,
                published_at=datetime.now(timezone.utc),
                error_message=None,
            )
        )
        await session.commit()
        result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
        return _to_domain(result.scalar_one())
