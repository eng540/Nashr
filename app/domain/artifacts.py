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
