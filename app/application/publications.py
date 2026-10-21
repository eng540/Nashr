from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pypdf import PdfReader, PdfWriter
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.editorial import IEditorialDrafter
from app.application.control_plane import ControlPlaneResolver
from app.domain.publications import IPublisher, Publication, PublicationStatus
from app.domain.artifacts import Artifact, ArtifactKind
from app.domain.quizzes import QuizPayload
from app.application.posts import ProducePost
from app.application.artifacts import load_post_model_to_artifact, post_model_to_artifact, post_to_artifact
from app.application.editorial_context import slice_pdf_pages_as_bytes
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, PostModel, PublicationModel
from app.infrastructure.artifact_storage import ArtifactStorageError, S3ArtifactStorage


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
        artifact_id=row.artifact_id,
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
        is_post = artifact.kind == ArtifactKind.POST
        reference_filter = PublicationModel.post_id == artifact.id if is_post else PublicationModel.artifact_id == artifact.id
        existing_result = await session.execute(
            select(PublicationModel)
            .where(
                reference_filter,
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
            post_id=artifact.id if is_post else None,
            artifact_id=None if is_post else artifact.id,
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
                    reference_filter,
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
            if publication_row.artifact_id is not None:
                from app.application.artifacts import load_artifact
                artifact = await load_artifact(session, publication_row.artifact_id)
                if artifact is None:
                    raise ValueError("Publication Artifact not found.")
            elif publication_row.post_id is not None:
                artifact = await load_post_model_to_artifact(session, publication_row.post_id)
            else:
                raise ValueError("Publication must reference a Post or generic Artifact.")

        artifact_review_status = None
        if artifact.kind != ArtifactKind.POST:
            artifact_row = (await session.execute(
                select(ArtifactModel).where(ArtifactModel.id == artifact.id)
            )).scalar_one_or_none()
            if artifact_row is None or artifact_row.status != "AVAILABLE":
                raise ValueError("Artifact must be AVAILABLE before publication.")
            artifact_review_status = artifact_row.review_status
        approved = artifact.editorial_status == "APPROVED" if artifact.kind == ArtifactKind.POST else artifact_review_status == "APPROVED"
        if not approved:
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
            if not (
                (artifact.kind == ArtifactKind.POST and current_row.post_id == artifact.id)
                or (artifact.kind != ArtifactKind.POST and current_row.artifact_id == artifact.id)
            ):
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
        if not (
            (artifact.kind == ArtifactKind.POST and current_row.post_id == artifact.id)
            or (artifact.kind != ArtifactKind.POST and current_row.artifact_id == artifact.id)
        ):
            raise ValueError("Publication does not belong to the supplied Artifact.")
        if current_row.status != PublicationStatus.DRAFT.value:
            raise ValueError("Publication is not a DRAFT.")

        media_bytes = None
        media_mime_type = None
        quiz_payload = None
        if artifact.kind == ArtifactKind.QUIZ:
            metadata = artifact.metadata or {}
            quiz_data = metadata.get("quiz")
            if not isinstance(quiz_data, dict):
                raise ValueError("Approved QUIZ Artifact has no structured quiz payload.")
            quiz_payload = QuizPayload.from_dict(quiz_data)
            if artifact.content != quiz_payload.question:
                raise ValueError("QUIZ Artifact question does not match its approved content.")
        post_result = await session.execute(select(PostModel).where(PostModel.id == artifact.id))
        post_row = post_result.scalar_one_or_none()
        if post_row is not None and post_row.visual_artifact_id is not None:
            visual_result = await session.execute(
                select(ArtifactModel).where(ArtifactModel.id == post_row.visual_artifact_id)
            )
            visual = visual_result.scalar_one_or_none()
            if (
                visual is None
                or visual.kind != "IMAGE"
                or visual.status != "AVAILABLE"
                or visual.review_status != "APPROVED"
                or not visual.storage_uri
                or visual.mime_type not in {"image/png", "image/jpeg", "image/webp"}
                or visual.source_knowledge_unit_id != post_row.knowledge_unit_id
            ):
                raise ValueError("The attached visual Artifact is no longer approved or available for Publishing.")
            visual_metadata = visual.artifact_metadata or {}
            source_type = visual_metadata.get("source_type", "TEXT_ARTIFACT")
            source_text_hash = visual_metadata.get("source_text_sha256")
            if source_type == "POST":
                if visual_metadata.get("source_post_id") != str(post_row.id) or visual_metadata.get("source_id") != str(post_row.id):
                    raise ValueError("The attached visual was not produced from this Post.")
                if post_row.content is None or source_text_hash != hashlib.sha256(post_row.content.encode("utf-8")).hexdigest():
                    raise ValueError("The Post text no longer matches the approved text used to create the visual.")
            elif source_type == "TEXT_ARTIFACT":
                source_artifact_value = visual_metadata.get("source_artifact_id")
                try:
                    source_artifact_id = UUID(str(source_artifact_value))
                except (TypeError, ValueError) as exc:
                    raise ValueError("The attached visual Artifact has invalid approved-text provenance.") from exc
                source_text = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == source_artifact_id))).scalar_one_or_none()
                if (
                    source_text is None or source_text.kind != "TEXT" or source_text.status != "AVAILABLE"
                    or source_text.review_status != "APPROVED" or source_text.content is None
                    or source_text.source_knowledge_unit_id != post_row.knowledge_unit_id
                    or source_text.content != post_row.content
                    or source_text_hash != hashlib.sha256(source_text.content.encode("utf-8")).hexdigest()
                ):
                    raise ValueError("The Post text no longer matches the approved TEXT Artifact used to create the visual.")
            else:
                raise ValueError("The attached visual has missing or unsupported source provenance.")
            try:
                media_bytes = await S3ArtifactStorage.from_environment().get_bytes(visual.storage_uri)
            except (ArtifactStorageError, ValueError) as exc:
                raise ValueError("The approved visual Artifact could not be read from private storage.") from exc
            media_mime_type = visual.mime_type

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
            if quiz_payload is not None:
                if row.content != quiz_payload.question:
                    raise ValueError("Publication content no longer matches the approved quiz question.")
                published = await self.publisher.publish(
                    destination=row.destination, content=row.content, quiz=quiz_payload
                )
            elif media_bytes is None:
                published = await self.publisher.publish(destination=row.destination, content=row.content)
            else:
                published = await self.publisher.publish(
                    destination=row.destination,
                    content=row.content,
                    media=media_bytes,
                    media_mime_type=media_mime_type,
                )
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
