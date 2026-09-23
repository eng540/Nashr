from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

class SourceStatus(StrEnum):
    """Define the source lifecycle states."""
    STORED = "STORED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"

@dataclass(frozen=True)
class Source:
    """Represent a stored source file and its lifecycle state."""
    id: UUID
    filename: str
    mime_type: str
    storage_path: str
    size_bytes: int
    status: SourceStatus
    created_at: datetime

    @classmethod
    def stored(cls, filename: str, mime_type: str, storage_path: str, size_bytes: int) -> "Source":
        """Create a source that has been successfully stored."""
        return cls(uuid4(), filename, mime_type, storage_path, size_bytes, SourceStatus.STORED, datetime.now(timezone.utc))
