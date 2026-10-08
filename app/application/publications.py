from __future__ import annotations

import io
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import TYPE_CHECKING

from pypdf import PdfReader, PdfWriter
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.editorial import IEditorialDrafter
from app.application.control_plane import ControlPlaneResolver
from app.domain.publications import IPublisher, Publication, PublicationStatus
from app.domain.artifacts import Artifact
from app.application.posts import ProducePost
from app.application.artifacts import load_post_model_to_artifact, post_model_to_artifact, post_to_artifact
from app.application.editorial_context import slice_pdf_pages_as_bytes
from app.infrastructure.database.models import KnowledgeUnitModel, PublicationModel

if TYPE_CHECKING:
    from app.infrastructure.database.models import PostModel


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

    def __init__(self, drafter: IEditorialDrafter, resolver: ControlPlaneResolver | None = None) -> None:
        self.drafter = drafter
        self.resolver = resolver or ControlPlaneResolver()

    async def execute(self, session: AsyncSession, knowledge_unit_id: UUID, destination: str) -> Publication:
        post = await ProducePost(self.drafter, self.resolver).execute(session, knowledge_unit_id)
        return await self.execute_for_artifact(session, post_to_artifact(post), destination)

    @staticmethod
    async def execute_for_post(session: AsyncSession, post: PostModel, destination: str) -> Publication:
        return await CreateTelegramDraft.execute_for_artifact(session, post_model_to_artifact(post), destination)

    @staticmethod
    async def execute_for_artifact(session: AsyncSession, artifact: Artifact, destination: str) -> Publication:
        existing_result = await session.execute(
            select(PublicationModel)
            .where(
                PublicationModel.post_id == artifact.id,
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
            knowledge_unit_id=artifact.source_knowledge_unit_id,
            post_id=artifact.id,
            platform="telegram",
            destination=destination,
            content=artifact.content,
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
                    PublicationModel.post_id == artifact.id,
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

    async def execute(
        self,
        session: AsyncSession,
        publication_id: UUID,
        content: str | None = None,
        artifact: Artifact | None = None,
    ) -> Publication:
        """Persist optional edits, then publish the supplied Artifact.

        The PostModel fallback is a compatibility edge for existing callers and
        persistence contracts. Core publication checks operate only on Artifact.
        """
        if artifact is None:
            publication_result = await session.execute(
                select(PublicationModel).where(PublicationModel.id == publication_id)
            )
            publication_row = publication_result.scalar_one_or_none()
            if publication_row is None:
                raise ValueError("Publication not found.")
            if publication_row.post_id is None:
                raise ValueError("Publication requires an Artifact-backed Post.")
            artifact = await load_post_model_to_artifact(session, publication_row.post_id)

        if artifact.status != "APPROVED":
            raise ValueError("Artifact must be APPROVED before publication.")
        if content is not None:
            content = content.strip()
            if not content:
                raise ValueError("Publication content cannot be empty.")
            if content != artifact.content:
                raise ValueError("Edit and approve the Artifact before publication.")

            current = await session.execute(
                select(PublicationModel).where(
                    PublicationModel.id == publication_id,
                    PublicationModel.status == PublicationStatus.DRAFT.value,
                )
            )
            current_row = current.scalar_one_or_none()
            if current_row is None:
                raise ValueError("Publication is not a DRAFT.")
            if current_row.post_id != artifact.id:
                raise ValueError("Publication does not belong to the supplied Artifact.")
            edited = await session.execute(
                update(PublicationModel)
                .where(
                    PublicationModel.id == publication_id,
                    PublicationModel.status == PublicationStatus.DRAFT.value,
                )
                .values(content=content)
            )
            if edited.rowcount != 1:
                raise ValueError("Publication is not a DRAFT.")
            await session.commit()

        current = await session.execute(
            select(PublicationModel).where(PublicationModel.id == publication_id)
        )
        current_row = current.scalar_one_or_none()
        if current_row is None:
            raise ValueError("Publication not found.")
        if current_row.post_id != artifact.id:
            raise ValueError("Publication does not belong to the supplied Artifact.")
        if content is None:
            current_row.content = artifact.content
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
