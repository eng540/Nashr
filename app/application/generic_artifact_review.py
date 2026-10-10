from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.output_contracts import OutputContractDefinition
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

    async def list(self, review_status: str = "DRAFT", limit: int = 50) -> list[dict[str, Any]]:
        if review_status not in {"DRAFT", "APPROVED", "REJECTED"}:
            raise ValueError("Unsupported artifact review status.")
        rows = (await self.session.execute(
            select(ArtifactModel)
            .where(ArtifactModel.kind != "POST", ArtifactModel.review_status == review_status)
            .order_by(ArtifactModel.created_at.desc(), ArtifactModel.id.desc())
            .limit(limit)
        )).scalars().all()
        return [_payload(row) for row in rows]

    async def get(self, artifact_id: UUID) -> dict[str, Any]:
        row = await self._get_row(artifact_id)
        return _payload(row)

    async def update(self, artifact_id: UUID, content: str | None, metadata: dict[str, Any] | None) -> dict[str, Any]:
        row = await self._get_row(artifact_id, for_update=True)
        if row.review_status != "DRAFT":
            raise ValueError("Only DRAFT generic artifacts can be edited.")
        candidate_content = row.content if content is None else content
        candidate_metadata = dict(row.artifact_metadata or {}) if metadata is None else dict(metadata)
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
        row.review_status = "APPROVED"
        row.review_note = review_note.strip() if review_note and review_note.strip() else None
        row.reviewed_at = datetime.now(timezone.utc)
        row.updated_at = row.reviewed_at
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
