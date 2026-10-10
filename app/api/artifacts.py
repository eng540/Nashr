from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.generic_artifact_review import GenericArtifactReviewService
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
