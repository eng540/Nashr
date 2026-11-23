from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.output_contracts import OutputContractDefinition
from app.domain.quizzes import QuizPayload
from app.domain.policies import ProductionPolicyDefinition
from app.domain.production_context import PinnedOutputContract, PinnedPolicy
from app.infrastructure.database.models import ArtifactModel


def _payload(row: ArtifactModel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "source_knowledge_unit_id": str(row.source_knowledge_unit_id),
        "kind": row.kind,
        "status": row.status,
        "content": row.content,
        "storage_uri": row.storage_uri,
        "mime_type": row.mime_type,
        "output_contract_key": row.output_contract_key,
        "output_contract_version": row.output_contract_version,
        "metadata": row.artifact_metadata or {},
        "review_status": row.review_status,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_review_candidate(row: ArtifactModel, content: str | None, metadata: dict[str, Any]) -> None:
    if row.kind == "POST":
        raise ValueError("POST artifacts must use the canonical Post review workflow.")
    context = row.resolved_context or {}
    if "output_contract" not in context:
        raise ValueError("Artifact has no pinned output contract and cannot be reviewed safely.")
    pinned = PinnedOutputContract.from_dict(context["output_contract"])
    definition = OutputContractDefinition.from_dict(pinned.definition)
    if definition.artifact_kind != row.kind or definition.mime_type != row.mime_type:
        raise ValueError("Artifact provenance does not match its pinned output contract.")
    missing = [field for field in definition.required_metadata_fields if field not in metadata]
    if missing:
        raise ValueError("Artifact is missing required metadata fields: " + ", ".join(missing))
    if metadata.get("telegram_native") is not None:
        from app.domain.telegram_payloads import native_payload
        if row.kind != "TEXT":
            raise ValueError("Native Telegram content must use TEXT.")
        native_payload(metadata["telegram_native"])
    if metadata.get("telegram_album") is not None:
        from app.domain.telegram_albums import album_ids
        if row.kind != "TEXT" or metadata.get("telegram_native") is not None:
            raise ValueError("Album must be a dedicated TEXT wrapper.")
        album_ids(metadata["telegram_album"])
    if metadata.get('telegram_live_photo') is not None:
        from app.application.telegram_live_photos import pair_ids
        if row.kind != 'TEXT' or metadata.get('telegram_native') is not None or metadata.get('telegram_album') is not None:
            raise ValueError('Live Photo requires a dedicated TEXT wrapper.')
        pair_ids(metadata)
    if row.kind == "QUIZ":
        payload = metadata.get("quiz")
        if not isinstance(payload, dict):
            raise ValueError("QUIZ Artifact requires structured quiz metadata.")
        from_payload = QuizPayload.from_dict(payload)
        if content != from_payload.question:
            raise ValueError("QUIZ Artifact content must match its structured question.")
    if definition.content_mode == "INLINE":
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Inline artifact content cannot be empty.")
        if definition.max_content_chars is not None and len(content) > definition.max_content_chars:
            raise ValueError("Artifact content exceeds the pinned output contract limit.")
        if row.storage_uri is not None:
            raise ValueError("Inline artifact cannot also reference stored media.")
    else:
        if content is not None or not row.storage_uri:
            raise ValueError("Storage-backed artifact must retain its storage URI and cannot contain inline text.")
    if "policy" in context and content is not None:
        policy = ProductionPolicyDefinition.from_dict(PinnedPolicy.from_dict(context["policy"]).definition)
        errors = policy.validate_content(content)
        if errors:
            raise ValueError("Artifact violates pinned production policy: " + " ".join(errors))


class GenericArtifactReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, review_status: str = "DRAFT", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if review_status not in {"DRAFT", "APPROVED", "REJECTED"}:
            raise ValueError("Unsupported artifact review status.")
        if offset < 0:
            raise ValueError("offset must be zero or greater.")
        filters = [ArtifactModel.kind != "POST", ArtifactModel.review_status == review_status]
        total = (await self.session.execute(
            select(func.count()).select_from(ArtifactModel).where(*filters)
        )).scalar_one()
        rows = (await self.session.execute(
            select(ArtifactModel)
            .where(*filters)
            .order_by(ArtifactModel.created_at.desc(), ArtifactModel.id.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
        return {"items": [_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    async def get(self, artifact_id: UUID) -> dict[str, Any]:
        row = await self._get_row(artifact_id)
        return _payload(row)

    async def update(self, artifact_id: UUID, content: str | None, metadata: dict[str, Any] | None) -> dict[str, Any]:
        row = await self._get_row(artifact_id, for_update=True)
        if row.review_status != "DRAFT":
            raise ValueError("Only DRAFT generic artifacts can be edited.")
        candidate_content = row.content if content is None else content
        candidate_metadata = dict(row.artifact_metadata or {}) if metadata is None else dict(metadata)
        if (row.artifact_metadata or {}).get("telegram_album") is not None:
            keys = ("telegram_album", "album_child_fingerprints", "album_preview")
            if any(candidate_metadata.get(key) != row.artifact_metadata.get(key) for key in keys):
                raise ValueError("Album selection and preview are immutable; create a new album.")
        elif candidate_metadata.get("telegram_album") is not None:
            raise ValueError("Use the dedicated album creation workflow.")
        if (row.artifact_metadata or {}).get('telegram_live_photo') is not None:
            keys = ('telegram_live_photo', 'live_photo_fingerprints', 'live_photo_preview')
            if any(candidate_metadata.get(key) != row.artifact_metadata.get(key) for key in keys):
                raise ValueError('Live Photo pair and preview are immutable.')
        elif candidate_metadata.get('telegram_live_photo') is not None:
            raise ValueError('Use the dedicated Live Photo creation workflow.')
        _validate_review_candidate(row, candidate_content, candidate_metadata)
        row.content = candidate_content
        row.artifact_metadata = candidate_metadata
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return _payload(row)

    async def approve(self, artifact_id: UUID, review_note: str | None = None) -> dict[str, Any]:
        row = await self._get_row(artifact_id, for_update=True)
        if row.review_status != "DRAFT":
            raise ValueError("Only DRAFT generic artifacts can be approved.")
        _validate_review_candidate(row, row.content, dict(row.artifact_metadata or {}))
        if (row.artifact_metadata or {}).get("telegram_album") is not None:
            from app.application.telegram_albums import resolve_album
            await resolve_album(self.session, row.artifact_metadata)
        if (row.artifact_metadata or {}).get('telegram_live_photo') is not None:
            from app.application.telegram_live_photos import resolve_live_photo
            await resolve_live_photo(self.session, row.artifact_metadata)
        row.review_status = "APPROVED"
        row.review_note = review_note.strip() if review_note and review_note.strip() else None
        row.reviewed_at = datetime.now(timezone.utc)
        row.updated_at = row.reviewed_at
        await self.session.commit()
        await self.session.refresh(row)
        return _payload(row)

    async def record_manual_publication(
        self, artifact_id: UUID, published_at: datetime, external_url: str | None = None
    ) -> dict[str, Any]:
        row = await self._get_row(artifact_id, for_update=True)
        if row.kind == "POST":
            raise ValueError("POST artifacts must use the canonical Post publication workflow.")
        if row.review_status != "APPROVED":
            raise ValueError("Only APPROVED artifacts can be recorded as manually published.")
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if published_at > now + timedelta(minutes=5):
            raise ValueError("Manual publication date cannot be in the future.")
        cleaned_url = external_url.strip() if external_url else None
        if cleaned_url == "":
            cleaned_url = None
        if cleaned_url is not None and not cleaned_url.startswith(("http://", "https://")):
            raise ValueError("External URL must start with http:// or https://.")
        metadata = dict(row.artifact_metadata or {})
        metadata["manual_publication"] = {
            "published_at": published_at.isoformat(),
            "external_url": cleaned_url,
            "recorded_at": now.isoformat(),
        }
        row.artifact_metadata = metadata
        row.updated_at = now
        await self.session.commit()
        await self.session.refresh(row)
        return _payload(row)

    async def reject(self, artifact_id: UUID, review_note: str) -> dict[str, Any]:
        row = await self._get_row(artifact_id, for_update=True)
        if row.review_status != "DRAFT":
            raise ValueError("Only DRAFT generic artifacts can be rejected.")
        if not review_note.strip():
            raise ValueError("A rejection reason is required.")
        row.review_status = "REJECTED"
        row.review_note = review_note.strip()
        row.reviewed_at = datetime.now(timezone.utc)
        row.updated_at = row.reviewed_at
        await self.session.commit()
        await self.session.refresh(row)
        return _payload(row)

    async def _get_row(self, artifact_id: UUID, *, for_update: bool = False) -> ArtifactModel:
        statement = select(ArtifactModel).where(ArtifactModel.id == artifact_id)
        if for_update:
            statement = statement.with_for_update()
        row = (await self.session.execute(statement)).scalar_one_or_none()
        if row is None or row.kind == "POST":
            raise LookupError("Generic Artifact not found.")
        if row.review_status is None:
            raise ValueError("Artifact does not have a generic review state.")
        return row
