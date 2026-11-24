from __future__ import annotations
from app.domain.telegram_copy import telegram_publish_text

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
from app.application.media_bank import MEDIA_KINDS
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
        external_ids=tuple(row.external_ids or ()),
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
    async def execute_for_artifact(
        session: AsyncSession, artifact: Artifact, destination: str, content_override: str | None = None, connection_id: UUID | None = None
    ) -> Publication:
        destinations={destination}
        if connection_id is None:
            from app.application.managed_connections import default_binding
            default_destination,default_id=await default_binding(session)
            if destination==default_destination:connection_id=default_id
        if connection_id:
            from app.application.managed_connections import selected,allowed_destinations
            channel,_=await selected(session,connection_id)
            destinations=allowed_destinations(channel)
            if destination not in destinations:raise ValueError('الوجهة لا تطابق هوية الربط.')
        is_post = artifact.kind == ArtifactKind.POST
        reference_filter = PublicationModel.post_id == artifact.id if is_post else PublicationModel.artifact_id == artifact.id
        existing_result = await session.execute(
            select(PublicationModel)
            .where(
                reference_filter,
                PublicationModel.platform == "telegram",
                PublicationModel.destination.in_(destinations),
            )
            .order_by(PublicationModel.created_at.asc(), PublicationModel.id.asc())
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if connection_id is not None and existing.connection_id!=connection_id:raise ValueError("Existing publication belongs to a different bot binding; review it before continuing.")
            return _to_domain(existing)

        row = PublicationModel(
            id=uuid4(),
            knowledge_unit_id=artifact.source_knowledge_unit_id,
            post_id=artifact.id if is_post else None,
            artifact_id=None if is_post else artifact.id,
            platform="telegram",
            connection_id=connection_id,
            destination=destination,
            content=content_override if content_override is not None else artifact.content,
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

    def __init__(self, publisher: IPublisher | None = None) -> None:
        """Initialize the publisher."""
        self.publisher = publisher

    async def execute(
        self,
        session: AsyncSession,
        publication_id: UUID,
        content: str | None = None,
        artifact: Artifact | None = None,
        reviewed_copy_text: str | None = None,
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

        bound_publication=await session.get(PublicationModel,publication_id)
        if bound_publication and not bound_publication.connection_id:
            from app.application.managed_connections import bind_legacy_publication
            await bind_legacy_publication(session,bound_publication)
        if bound_publication and bound_publication.connection_id:
            from app.application.managed_connections import publication_publisher
            self.publisher=await publication_publisher(session,bound_publication)
        artifact_review_status = None
        if artifact.kind != ArtifactKind.POST:
            artifact_row = (await session.execute(
                select(ArtifactModel).where(ArtifactModel.id == artifact.id)
            )).scalar_one_or_none()
            if artifact_row is None or artifact_row.status != "AVAILABLE":
                raise ValueError("Artifact must be AVAILABLE before publication.")
            artifact_review_status = artifact_row.review_status
            # Always use the current approved record, not a caller's stale copy.
            from app.application.artifacts import load_artifact
            artifact = await load_artifact(session, artifact_row.id)
            if artifact is None:
                raise ValueError("Approved Artifact could not be loaded.")
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

        album_media = None
        live_photo_media = None
        media_bytes = None
        media_mime_type = None
        quiz_payload = None
        if (artifact.metadata or {}).get("telegram_album") is not None:
            from app.application.telegram_albums import resolve_album
            children, _ = await resolve_album(session, artifact.metadata)
            album_media = []
            total_bytes = 0
            storage = S3ArtifactStorage.from_environment()
            from app.domain.telegram_media import media_request
            for child in children:
                data = await storage.get_bytes(child.storage_uri, max_bytes=min(50 * 1024 * 1024, 100 * 1024 * 1024 - total_bytes))
                total_bytes += len(data)
                if total_bytes > 100 * 1024 * 1024:
                    raise ValueError("Album exceeds100MiB total upload limit.")
                meta = child.artifact_metadata or {}
                media_request(child.kind, child.mime_type, data, meta.get("original_filename"))
                album_media.append({"kind": child.kind, "mime_type": child.mime_type, "data": data,
                    "filename": meta.get("original_filename"), "caption": str(meta.get("caption") or "")})
        if (artifact.metadata or {}).get('telegram_live_photo') is not None:
            from app.application.telegram_live_photos import resolve_live_photo
            from app.domain.telegram_live_photo import validate_live_motion
            from app.domain.telegram_media import media_request
            children, _ = await resolve_live_photo(session, artifact.metadata)
            storage = S3ArtifactStorage.from_environment()
            photo = await storage.get_bytes(children[0].storage_uri, max_bytes=10 * 1024 * 1024)
            motion = await storage.get_bytes(children[1].storage_uri, max_bytes=10 * 1024 * 1024)
            media_request('IMAGE', children[0].mime_type, photo)
            validate_live_motion(motion)
            live_photo_media = {'photo': photo, 'photo_mime': children[0].mime_type, 'motion': motion}
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
        if artifact.kind.value in MEDIA_KINDS:
            if not artifact.storage_uri:
                raise ValueError("Approved media Artifact has no storage reference.")
            try:
                media_bytes = await S3ArtifactStorage.from_environment().get_bytes(artifact.storage_uri)
            except (ArtifactStorageError, ValueError) as exc:
                raise ValueError("The approved media Artifact could not be read from private storage.") from exc
            media_mime_type = artifact.mime_type
        elif post_row is not None and post_row.visual_artifact_id is not None:
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

        if reviewed_copy_text is not None and artifact.kind != ArtifactKind.POST:
            current_row.content = reviewed_copy_text
            await session.commit()
        elif content is None and artifact.kind != ArtifactKind.POST:
            current_row.content = telegram_publish_text(artifact)
            await session.commit()
        elif content is None and artifact.content is not None:
            current_row.content = artifact.content
            await session.commit()

        # Share the local lifecycle lock through the READY transition. A disable
        # cannot pass the final check then race a newly starting provider call.
        from sqlalchemy import text
        await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
        await session.refresh(bound_publication)
        from app.application.managed_connections import bind_legacy_publication
        if not bound_publication.connection_id:await bind_legacy_publication(session,bound_publication)
        if bound_publication.connection_id:
            from app.application.managed_connections import publication_publisher
            self.publisher=await publication_publisher(session,bound_publication)
        if self.publisher is None:
            from app.adapters.publishing.telegram import TelegramPublisher
            self.publisher=TelegramPublisher()
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
            if live_photo_media is not None:
                published = await self.publisher.publish(destination=row.destination, content=row.content, live_photo=live_photo_media)
            elif album_media is not None:
                published = await self.publisher.publish(destination=row.destination, content=row.content, album=album_media)
            elif quiz_payload is not None:
                if row.content != quiz_payload.question:
                    raise ValueError("Publication content no longer matches the approved quiz question.")
                published = await self.publisher.publish(
                    destination=row.destination, content=row.content, quiz=quiz_payload
                )
            elif media_bytes is None:
                published = await self.publisher.publish(destination=row.destination, content=row.content,
                    **({"native": (artifact.metadata or {})["telegram_native"]} if (artifact.metadata or {}).get("telegram_native") is not None else {}))
            else:
                published = await self.publisher.publish(
                    destination=row.destination,
                    content=row.content,
                    media=media_bytes,
                    media_mime_type=media_mime_type,
                    **({"media_kind": artifact.kind.value,
                        "media_filename": str((artifact.metadata or {}).get("original_filename") or "")}
                       if artifact.kind.value in MEDIA_KINDS - {"IMAGE", "VIDEO"} else {}),
                )
        except Exception as exc:
            await session.execute(
                update(PublicationModel)
                .where(PublicationModel.id == publication_id)
                .values(status=PublicationStatus.PUBLISHING.value if album_media is not None or live_photo_media is not None or (artifact.metadata or {}).get("telegram_native", {}).get("type") == "LIVE_LOCATION" else PublicationStatus.FAILED.value, error_message=str(exc))
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
                external_ids=list(published.external_ids) or [published.external_id],
                published_at=datetime.now(timezone.utc),
                error_message=None,
            )
        )
        await session.commit()
        result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
        return _to_domain(result.scalar_one())
