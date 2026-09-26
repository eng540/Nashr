from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True)
class KnowledgeUnit:
    """Represent one persisted material discovered from a source."""
    id: UUID
    source_id: UUID
    position: int
    title: str
    content: str
    original_text: str | None
    source_reference: str | None
    created_at: datetime

    @classmethod
    def from_extracted(cls, source_id: UUID, position: int, title: str, content: str, original_text: str | None = None, source_reference: str | None = None) -> "KnowledgeUnit":
        """Create a knowledge unit from one discovered material."""
        return cls(uuid4(), source_id, position, title, content, original_text, source_reference, datetime.now(timezone.utc))
