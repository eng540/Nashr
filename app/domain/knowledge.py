from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True)
class KnowledgeUnit:
    """Represent one persisted knowledge unit extracted from a source."""
    id: UUID
    source_id: UUID
    position: int
    title: str
    content: str
    created_at: datetime

    @classmethod
    def from_extracted(cls, source_id: UUID, position: int, title: str, content: str) -> "KnowledgeUnit":
        """Create a knowledge unit from one extracted idea."""
        return cls(uuid4(), source_id, position, title, content, datetime.now(timezone.utc))
