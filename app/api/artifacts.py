from typing import Any
from datetime import datetime
import os
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.generic_artifact_review import GenericArtifactReviewService
from app.application.artifacts import load_artifact
from app.application.media_bank import IngestReadyMedia
from app.application.publications import CreateTelegramDraft
from app.domain.artifacts import ArtifactKind
from app.application.scheduling import validate_timezone, validate_scheduled_at
from app.domain.scheduling import ScheduleItemStatus, ScheduleStatus
from app.infrastructure.database.models import ArtifactModel, PublicationModel, ScheduleItemModel, ScheduleModel
from sqlalchemy import select
from app.infrastructure.artifact_storage import (
    ArtifactStorageConfigurationError,
    ArtifactStorageError,
    S3ArtifactStorage,
)
from app.infrastructure.database.session import get_session


router = APIRouter(prefix="/api/artifacts", tags=["generic-artifact-review"])


class ArtifactReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str | None = Field(default=None, max_length=100000)
    metadata: dict[str, Any] | None = None


class ArtifactReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_note: str | None = Field(default=None, max_length=2000)


class QuizScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    timezone: str = Field(min_length=1, max_length=100)
    scheduled_at: datetime


class PlatformVariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(min_length=1, max_length=30)


class ArtifactRejectDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_note: str = Field(min_length=1, max_length=2000)


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("")
async def list_generic_artifacts(
    review_status: str = Query(default="DRAFT"),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    try:
        return await GenericArtifactReviewService(session).list(review_status, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ingest-media", status_code=201)
async def ingest_ready_media(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=1024),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Ingest a ready-made image/video into the media bank as a DRAFT Artifact.

    No generation provider is involved; the upload is stored in private media
    storage and enters the standard generic artifact review flow.
    """
    data = await file.read()
    try:
        artifact = await IngestReadyMedia().execute(
            session,
            filename=file.filename or "media",
            content_type=file.content_type or "",
            data=data,
            caption=caption,
        )
        return await GenericArtifactReviewService(session).get(artifact.id)
    except ArtifactStorageConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArtifactStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{artifact_id}/platform-variant", status_code=201)
async def derive_platform_variant(
    artifact_id: UUID,
    input: PlatformVariantRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Derive a DRAFT per-platform variant from an APPROVED generic Artifact.

    Preparation only: text is trimmed to the target platform's documented
    constraints and the constraint provenance is stored in metadata. No
    external publishing happens here.
    """
    from app.application.platform_variants import DerivePlatformVariant

    try:
        artifact = await DerivePlatformVariant().execute(session, artifact_id=artifact_id, platform=input.platform)
        return await GenericArtifactReviewService(session).get(artifact.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{artifact_id}")
async def get_generic_artifact(artifact_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await GenericArtifactReviewService(session).get(artifact_id)
    except (LookupError, ValueError) as exc:
        raise _handle_error(exc) from exc


@router.get("/{artifact_id}/media-url")
async def get_generic_artifact_media_url(
    artifact_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        artifact = await GenericArtifactReviewService(session).get(artifact_id)
        if artifact["kind"] not in {"IMAGE", "VIDEO", "AUDIO"} or not artifact["storage_uri"]:
            raise ValueError("Artifact does not contain storage-backed media.")
        storage = S3ArtifactStorage.from_environment()
        url = await storage.presign_get(artifact["storage_uri"], expires_seconds=300)
        return {"url": url, "expires_in": 300}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactStorageConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArtifactStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{artifact_id}")
async def update_generic_artifact(
    artifact_id: UUID, payload: ArtifactReviewUpdate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        return await GenericArtifactReviewService(session).update(artifact_id, payload.content, payload.metadata)
    except (LookupError, ValueError) as exc:
        raise _handle_error(exc) from exc


@router.post("/{artifact_id}/approve")
async def approve_generic_artifact(
    artifact_id: UUID, payload: ArtifactReviewDecision, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        return await GenericArtifactReviewService(session).approve(artifact_id, payload.review_note)
    except (LookupError, ValueError) as exc:
        raise _handle_error(exc) from exc


@router.post("/{artifact_id}/reject")
async def reject_generic_artifact(
    artifact_id: UUID, payload: ArtifactRejectDecision, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        return await GenericArtifactReviewService(session).reject(artifact_id, payload.review_note)
    except (LookupError, ValueError) as exc:
        raise _handle_error(exc) from exc


@router.post("/{artifact_id}/telegram-draft", status_code=201)
async def create_telegram_draft_for_artifact(
    artifact_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a durable Telegram publication draft for a human-approved generic QUIZ Artifact."""
    destination = os.getenv("TELEGRAM_DESTINATION_ID", "").strip()
    if not destination:
        raise HTTPException(status_code=503, detail="TELEGRAM_DESTINATION_ID is required.")
    try:
        review = await GenericArtifactReviewService(session).get(artifact_id)
        if review.get("kind") != ArtifactKind.QUIZ.value:
            raise ValueError("Only QUIZ Artifacts can use this native poll publication route.")
        if review.get("review_status") != "APPROVED":
            raise ValueError("QUIZ Artifact must be approved before creating a publication draft.")
        artifact = await load_artifact(session, artifact_id)
        if artifact is None:
            raise LookupError("Artifact not found.")
        publication = await CreateTelegramDraft.execute_for_artifact(session, artifact, destination)
        if publication.status.value == "FAILED":
            row = (await session.execute(select(PublicationModel).where(PublicationModel.id == publication.id))).scalar_one()
            row.status = "DRAFT"
            row.error_message = None
            await session.commit()
            publication = await CreateTelegramDraft.execute_for_artifact(session, artifact, destination)
        return {
            "id": str(publication.id),
            "post_id": str(publication.post_id) if publication.post_id else None,
            "artifact_id": str(publication.artifact_id) if publication.artifact_id else None,
            "knowledge_unit_id": str(publication.knowledge_unit_id),
            "platform": publication.platform,
            "destination": publication.destination,
            "status": publication.status.value,
            "content": publication.content,
        }
    except (LookupError, ValueError) as exc:
        raise _handle_error(exc) from exc


@router.post("/{artifact_id}/telegram-media-draft", status_code=201)
async def create_telegram_media_draft_for_artifact(
    artifact_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a durable Telegram publication draft for an approved media bank Artifact."""
    destination = os.getenv("TELEGRAM_DESTINATION_ID", "").strip()
    if not destination:
        raise HTTPException(status_code=503, detail="TELEGRAM_DESTINATION_ID is required.")
    try:
        review = await GenericArtifactReviewService(session).get(artifact_id)
        if review.get("kind") not in {ArtifactKind.IMAGE.value, ArtifactKind.VIDEO.value}:
            raise ValueError("Only IMAGE or VIDEO Artifacts can use this media publication route.")
        if review.get("review_status") != "APPROVED":
            raise ValueError("Media Artifact must be approved before creating a publication draft.")
        if not review.get("storage_uri"):
            raise ValueError("Media Artifact has no stored media to publish.")
        caption = str((review.get("metadata") or {}).get("caption") or "").strip()
        if not caption:
            raise ValueError("Media Artifact needs a non-empty caption before creating a publication draft.")
        artifact = await load_artifact(session, artifact_id)
        if artifact is None:
            raise LookupError("Artifact not found.")
        publication = await CreateTelegramDraft.execute_for_artifact(
            session, artifact, destination, content_override=caption
        )
        return {
            "id": str(publication.id),
            "post_id": str(publication.post_id) if publication.post_id else None,
            "artifact_id": str(publication.artifact_id) if publication.artifact_id else None,
            "knowledge_unit_id": str(publication.knowledge_unit_id),
            "platform": publication.platform,
            "destination": publication.destination,
            "status": publication.status.value,
            "content": publication.content,
        }
    except (LookupError, ValueError) as exc:
        raise _handle_error(exc) from exc


@router.post("/{artifact_id}/schedule", status_code=201)
async def schedule_approved_quiz(
    artifact_id: UUID,
    payload: QuizScheduleRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a one-item durable schedule for an approved QUIZ Artifact."""
    try:
        artifact_review = await GenericArtifactReviewService(session).get(artifact_id)
        if artifact_review.get("kind") != ArtifactKind.QUIZ.value:
            raise ValueError("Only QUIZ Artifacts can be scheduled through this route.")
        if artifact_review.get("review_status") != "APPROVED":
            raise ValueError("QUIZ Artifact must be approved before scheduling.")
        timezone_name = validate_timezone(payload.timezone)
        scheduled_at = validate_scheduled_at(payload.scheduled_at)
        already_published = (await session.execute(select(PublicationModel.id).where(
            PublicationModel.artifact_id == artifact_id,
            PublicationModel.platform == "telegram",
            PublicationModel.status == "PUBLISHED",
        ).limit(1))).scalar_one_or_none()
        if already_published is not None:
            raise ValueError("This quiz has already been published.")
        already_scheduled = (await session.execute(select(ScheduleItemModel.id).join(
            ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id
        ).where(
            ScheduleItemModel.artifact_id == artifact_id,
            ScheduleItemModel.status.in_(("PENDING", "PROCESSING", "PUBLISHED")),
            ScheduleModel.status.in_(("DRAFT", "ACTIVE", "PAUSED")),
        ).limit(1))).scalar_one_or_none()
        if already_scheduled is not None:
            raise ValueError("This quiz already belongs to an active or draft schedule.")
        artifact_row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == artifact_id))).scalar_one()
        if artifact_row.status != "AVAILABLE" or not artifact_row.content or not isinstance((artifact_row.artifact_metadata or {}).get("quiz"), dict):
            raise ValueError("QUIZ Artifact payload is incomplete or unavailable.")
        schedule = ScheduleModel(
            name=payload.name.strip(),
            timezone=timezone_name,
            status=ScheduleStatus.DRAFT.value,
        )
        schedule.items = [ScheduleItemModel(
            post_id=None,
            artifact_id=artifact_id,
            position=1,
            scheduled_at=scheduled_at,
            status=ScheduleItemStatus.PENDING.value,
        )]
        session.add(schedule)
        await session.commit()
        return {
            "id": str(schedule.id),
            "name": schedule.name,
            "status": schedule.status,
            "timezone": schedule.timezone,
            "items": [{
                "id": str(schedule.items[0].id),
                "artifact_id": str(artifact_id),
                "post_id": None,
                "scheduled_at": scheduled_at,
                "status": schedule.items[0].status,
            }],
        }
    except (LookupError, ValueError) as exc:
        await session.rollback()
        raise _handle_error(exc) from exc
