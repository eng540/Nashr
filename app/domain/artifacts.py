from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ArtifactKind(StrEnum):
    POST = "POST"
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"


class ArtifactStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class Artifact:
    """Durable, provider-neutral output contract.

    Editorial status remains owned by Post. Artifact status describes the output
    record itself; media outputs can use content or a storage reference.
    """

    id: UUID
    source_knowledge_unit_id: UUID
    kind: ArtifactKind
    content: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    storage_uri: str | None = None
    mime_type: str | None = None
    post_id: UUID | None = None
    editorial_status: str | None = None
    production_job_id: UUID | None = None
    output_contract_key: str | None = None
    output_contract_version: int | None = None
    resolved_context: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


def validate_production_artifact(
    artifact: Artifact,
    *,
    expected_job_id: UUID,
    expected_source_knowledge_unit_id: UUID,
) -> None:
    """Validate the shared minimum result contract before an item is marked complete.

    Provider-specific payload validation remains the capability's responsibility;
    this guard validates the provider-neutral Artifact envelope and its association.
    """
    if not isinstance(artifact, Artifact):
        raise TypeError("Production capability must return an Artifact result.")
    if not isinstance(artifact.id, UUID):
        raise ValueError("Production Artifact must have a valid identifier.")
    if artifact.source_knowledge_unit_id != expected_source_knowledge_unit_id:
        raise ValueError("Production Artifact belongs to a different source material.")
    if artifact.production_job_id is not None and artifact.production_job_id != expected_job_id:
        raise ValueError("Production Artifact belongs to a different production job.")
    try:
        kind = ArtifactKind(artifact.kind)
        status = ArtifactStatus(artifact.status)
    except ValueError as exc:
        raise ValueError("Production Artifact kind or status is unsupported.") from exc
    if status != ArtifactStatus.AVAILABLE:
        raise ValueError("Production Artifact must be AVAILABLE before item completion.")

    if kind in {ArtifactKind.POST, ArtifactKind.TEXT}:
        if not isinstance(artifact.content, str) or not artifact.content.strip():
            raise ValueError("Inline production Artifact must contain non-empty text.")
        if artifact.storage_uri is not None:
            raise ValueError("Inline production Artifact must not use a storage URI.")
        if kind == ArtifactKind.POST and artifact.post_id is None:
            raise ValueError("POST Artifact must reference its canonical Post.")
        return

    expected_mime_prefix = {
        ArtifactKind.IMAGE: "image/",
        ArtifactKind.VIDEO: "video/",
        ArtifactKind.AUDIO: "audio/",
    }.get(kind)
    if expected_mime_prefix is None:
        raise ValueError("Production Artifact kind is not supported by the shared contract.")
    if not isinstance(artifact.storage_uri, str) or not artifact.storage_uri.strip():
        raise ValueError("Media production Artifact requires a storage reference.")
    if artifact.content is not None:
        raise ValueError("Storage-backed media Artifact must not duplicate inline content.")
    if not isinstance(artifact.mime_type, str) or not artifact.mime_type.startswith(expected_mime_prefix):
        raise ValueError("Media production Artifact MIME type does not match its kind.")
