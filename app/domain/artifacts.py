from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ArtifactKind(StrEnum):
    POST = "POST"


@dataclass(frozen=True)
class Artifact:
    """Generic production output boundary.

    Post is the first concrete artifact kind. The boundary intentionally carries
    only production/output semantics and does not know about Telegram.
    """

    id: UUID
    source_knowledge_unit_id: UUID
    kind: ArtifactKind
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
