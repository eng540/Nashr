from app.domain.telegram_copy import telegram_publish_text
from typing import Any
from datetime import datetime
import os
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.generic_artifact_review import GenericArtifactReviewService
from app.application.artifacts import load_artifact
from app.application.media_bank import IngestReadyMedia, MEDIA_KINDS
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
    allow_length_trim: bool = False


class ArtifactRejectDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_note: str = Field(min_length=1, max_length=2000)


class ArtifactManualPublication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    published_at: datetime
    external_url: str | None = Field(default=None, max_length=2048)


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("")
async def list_generic_artifacts(
    review_status: str = Query(default="DRAFT"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await GenericArtifactReviewService(session).list(review_status, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ManualArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=100000)
    quiz: dict[str, Any] | None = None
    native: dict[str, Any] | None = None


@router.post("/manual-draft", status_code=201)
async def create_manual_draft(payload: ManualArtifactRequest, session: AsyncSession = Depends(get_session)):
    from app.application.manual_artifacts import create_manual_artifact
    try:
        artifact = await create_manual_artifact(session, **payload.model_dump())
        return await GenericArtifactReviewService(session).get(artifact.id)
    except (ValueError, TypeError) as exc:
        await session.rollback()
        raise HTTPException(422, str(exc)) from exc


class AlbumDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_ids: list[str] = Field(min_length=2, max_length=10)
    title: str = Field(min_length=1, max_length=500)


@router.post("/album-draft", status_code=201)
async def create_album_draft(payload: AlbumDraftRequest, session: AsyncSession = Depends(get_session)):
    from app.application.telegram_albums import create_album
    try:
        artifact = await create_album(session, **payload.model_dump())
        return await GenericArtifactReviewService(session).get(artifact.id)
    except (ValueError, TypeError) as exc:
        await session.rollback()
        raise HTTPException(422, str(exc)) from exc


class LivePhotoDraftRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    photo_id: str
    video_id: str
    title: str = Field(min_length=1, max_length=500)


@router.post('/live-photo-draft', status_code=201)
async def create_live_photo_draft(payload: LivePhotoDraftRequest, session: AsyncSession = Depends(get_session)):
    from app.application.telegram_live_photos import create_live_photo
    try:
        artifact = await create_live_photo(session, **payload.model_dump())
        return await GenericArtifactReviewService(session).get(artifact.id)
    except (ValueError, TypeError) as exc:
        await session.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/platform-variants")
async def list_platform_variant_drafts(
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List platform-variant drafts for the publishing workspace.

    Preparation-only: variants are never auto-scheduled or published; this
    listing only surfaces what has been prepared per platform for human
    review. Registered before "/{artifact_id}" so the literal path wins.
    """
    from app.application.platform_variants import list_platform_variants

    return await list_platform_variants(session, limit)


class PlatformCopyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict[str, Any]
    version: int = Field(ge=1)
    current_source_fingerprint: str


@router.get("/{artifact_id}/platform-copies")
async def platform_copies(artifact_id: UUID, session: AsyncSession = Depends(get_session)):
    from app.application.central_platform_copies import get_copies
    try:
        return await get_copies(session, artifact_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{artifact_id}/platform-copies/prepare")
async def prepare_platform_copies(artifact_id: UUID, session: AsyncSession = Depends(get_session)):
    from app.application.central_platform_copies import prepare_copies
    row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == artifact_id).with_for_update())).scalar_one_or_none()
    if row is None or row.review_status != 'APPROVED':
        raise HTTPException(422, 'اعتمد المادة الأصلية أولاً.')
    try:
        items = await prepare_copies(session, row)
        await session.commit()
        return {'artifact_id':str(artifact_id),'items':items}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.patch("/{artifact_id}/platform-copies/{platform}")
async def update_platform_copy(artifact_id: UUID, platform: str, payload: PlatformCopyUpdateRequest, session: AsyncSession = Depends(get_session)):
    from app.application.central_platform_copies import update_copy
    try:
        return await update_copy(session, artifact_id, platform, payload.fields, payload.version, payload.current_source_fingerprint)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(409, str(exc)) from exc


class TelegramBatchPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_ids: list[UUID] = Field(min_length=1, max_length=100)


@router.post("/telegram-batch-preview")
async def telegram_batch_preview(payload: TelegramBatchPreviewRequest, session: AsyncSession = Depends(get_session)):
    from app.application.telegram_batch_preview import preview_telegram_batch
    try:
        return await preview_telegram_batch(session, payload.artifact_ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class TelegramBatchScheduleRequest(TelegramBatchPreviewRequest):
    copy_versions: dict[str, int | None] = Field(default_factory=dict)
    fingerprints: dict[str, str]
    name: str = Field(min_length=1, max_length=300)
    timezone: str
    start_at: datetime
    interval_minutes: int = Field(ge=1, le=10080)
    destination: str


@router.post("/telegram-batch-schedule", status_code=201)
async def telegram_batch_schedule(payload: TelegramBatchScheduleRequest, session: AsyncSession = Depends(get_session)):
    from app.application.telegram_batch_schedule import create_telegram_batch_schedule
    try:
        data = payload.model_dump()
        data['timezone_name'] = data.pop('timezone')
        return await create_telegram_batch_schedule(session, **data)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(422, str(exc)) from exc


class DistributionSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_ids: list[UUID] = Field(min_length=1, max_length=100)
    platforms: list[str] = Field(max_length=6)
    fingerprints: dict[str, str]


@router.post("/distribution-selection")
async def save_distribution_selection(payload: DistributionSelectionRequest, session: AsyncSession = Depends(get_session)):
    from app.application.distribution_readiness import save_selection
    try:
        return await save_selection(session, payload.artifact_ids, payload.platforms, payload.fingerprints)
    except (ValueError, LookupError) as exc:
        await session.rollback()
        raise _handle_error(exc) from exc


@router.get("/{artifact_id}/distribution-readiness")
async def distribution_readiness(artifact_id: UUID, session: AsyncSession = Depends(get_session)):
    from app.application.distribution_readiness import get_readiness
    try:
        return await get_readiness(session, artifact_id)
    except LookupError as exc:
        raise _handle_error(exc) from exc


@router.post("/ingest-media", status_code=201)
async def ingest_ready_media(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=100000),
    media_kind: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Ingest a ready-made image/video into the media bank as a DRAFT Artifact.

    No generation provider is involved; the upload is stored in private media
    storage and enters the standard generic artifact review flow.
    """
    ingester = IngestReadyMedia()
    data = await file.read(ingester.max_bytes + 1)
    try:
        artifact = await ingester.execute(
            session,
            filename=file.filename or "media",
            content_type=file.content_type or "",
            data=data,
            caption=caption,
            media_kind=media_kind,
        )
        return await GenericArtifactReviewService(session).get(artifact.id)
    except ArtifactStorageConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArtifactStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/post-source/{post_id}/platform-variant", status_code=201)
async def derive_platform_variant_from_post(
    post_id: UUID,
    input: PlatformVariantRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Derive a DRAFT per-platform TEXT variant from an APPROVED editorial Post.

    Registered before the parameterized artifact route so the literal path wins.
    Preparation only: the Post is never modified; the variant is a separate
    review copy trimmed at safe boundaries with provenance metadata. No external
    publishing happens here.
    """
    from app.application.platform_variants import DerivePlatformVariant

    try:
        artifact = await DerivePlatformVariant().execute_post(session, post_id=post_id, platform=input.platform, allow_length_trim=input.allow_length_trim)
        return await GenericArtifactReviewService(session).get(artifact.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
        artifact = await DerivePlatformVariant().execute(session, artifact_id=artifact_id, platform=input.platform, allow_length_trim=input.allow_length_trim)
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
        if artifact["kind"] not in MEDIA_KINDS or not artifact["storage_uri"]:
            raise ValueError("Artifact does not contain storage-backed media.")
        storage = S3ArtifactStorage.from_environment()
        url = await storage.presign_get(artifact["storage_uri"], expires_seconds=300,
            **({"attachment_filename": str((artifact.get("metadata") or {}).get("original_filename") or "attachment.bin")} if artifact["kind"] == "DOCUMENT" else {}))
        return {"url": url, "expires_in": 300}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactStorageConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArtifactStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{artifact_id}/publications")
async def artifact_publication_ledger(artifact_id: UUID, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), session: AsyncSession = Depends(get_session)):
    from app.application.publication_ledger import artifact_publications
    try:
        return await artifact_publications(session, artifact_id, limit, offset)
    except (LookupError, ValueError) as exc:
        raise _handle_error(exc) from exc


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


@router.post("/{artifact_id}/manual-publication")
async def record_manual_publication(
    artifact_id: UUID,
    payload: ArtifactManualPublication,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Record that a human manually published an APPROVED artifact outside the app.

    Tracking only: no external call is made and nothing is auto-published. The
    record lives in artifact metadata so the publishing area can show the
    preparation-to-manual-publication pipeline truthfully.
    """
    try:
        return await GenericArtifactReviewService(session).record_manual_publication(
            artifact_id, payload.published_at, payload.external_url
        )
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
        if review.get("kind") not in {"QUIZ", "TEXT"}:
            raise ValueError("Only QUIZ or TEXT Artifacts can use this inline publication route.")
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
        if review.get("kind") not in MEDIA_KINDS | {"TEXT", "QUIZ"}:
            raise ValueError("Only supported media or TEXT Artifacts can use this publication route.")
        if review.get("review_status") != "APPROVED":
            raise ValueError("Media Artifact must be approved before creating a publication draft.")
        if review.get("kind") in MEDIA_KINDS and not review.get("storage_uri"):
            raise ValueError("Media Artifact has no stored media to publish.")
        artifact = await load_artifact(session, artifact_id)
        if artifact is None:
            raise LookupError("Artifact not found.")
        caption = telegram_publish_text(artifact)
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
    """Create a one-item durable schedule for an approved QUIZ or media Artifact."""
    try:
        artifact_review = await GenericArtifactReviewService(session).get(artifact_id)
        kind = artifact_review.get("kind")
        if kind not in MEDIA_KINDS | {"QUIZ", "TEXT"}:
            raise ValueError("Only supported Telegram Artifacts can be scheduled through this route.")
        if artifact_review.get("review_status") != "APPROVED":
            raise ValueError("Artifact must be approved before scheduling.")
        if kind in MEDIA_KINDS:
            if not artifact_review.get("storage_uri"):
                raise ValueError("Media Artifact has no stored media to schedule.")
        timezone_name = validate_timezone(payload.timezone)
        scheduled_at = validate_scheduled_at(payload.scheduled_at)
        already_published = (await session.execute(select(PublicationModel.id).where(
            PublicationModel.artifact_id == artifact_id,
            PublicationModel.platform == "telegram",
            PublicationModel.status == "PUBLISHED",
        ).limit(1))).scalar_one_or_none()
        if already_published is not None:
            raise ValueError("This Artifact has already been published.")
        already_scheduled = (await session.execute(select(ScheduleItemModel.id).join(
            ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id
        ).where(
            ScheduleItemModel.artifact_id == artifact_id,
            ScheduleItemModel.status.in_(("PENDING", "PROCESSING", "PUBLISHED")),
            ScheduleModel.status.in_(("DRAFT", "ACTIVE", "PAUSED")),
        ).limit(1))).scalar_one_or_none()
        if already_scheduled is not None:
            raise ValueError("This Artifact already belongs to an active or draft schedule.")
        artifact_row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == artifact_id))).scalar_one()
        if artifact_row.status != "AVAILABLE":
            raise ValueError("Artifact is unavailable.")
        if kind == ArtifactKind.QUIZ.value and (not artifact_row.content or not isinstance((artifact_row.artifact_metadata or {}).get("quiz"), dict)):
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


class LiveLocationOperationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: str
    latitude: float | None = None
    longitude: float | None = None


@router.get('/{artifact_id}/live-locations')
async def artifact_live_locations(artifact_id: UUID, session: AsyncSession = Depends(get_session)):
    from app.application.live_locations import list_live_locations
    try:
        return await list_live_locations(session, artifact_id)
    except ValueError as exc:
        raise _handle_error(exc) from exc


@router.post('/live-locations/{publication_id}/operations', status_code=201)
async def draft_location_operation(publication_id: UUID, payload: LiveLocationOperationRequest, session: AsyncSession = Depends(get_session)):
    from app.application.live_locations import create_operation
    try:
        return await create_operation(session, publication_id, **payload.model_dump())
    except ValueError as exc:
        await session.rollback()
        raise _handle_error(exc) from exc


@router.post('/live-location-operations/{operation_id}/execute')
async def confirm_location_operation(operation_id: UUID, session: AsyncSession = Depends(get_session)):
    from app.application.live_locations import execute_operation
    from app.adapters.publishing.telegram import TelegramPublisher
    try:
        return await execute_operation(session, operation_id, TelegramPublisher())
    except ValueError as exc:
        await session.rollback()
        raise _handle_error(exc) from exc


@router.post('/live-location-operations/{operation_id}/cancel')
async def cancel_location_operation(operation_id: UUID, session: AsyncSession = Depends(get_session)):
    from app.application.live_locations import cancel_operation
    try:
        return await cancel_operation(session, operation_id)
    except ValueError as exc:
        await session.rollback()
        raise _handle_error(exc) from exc
