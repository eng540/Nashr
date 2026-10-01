from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PostStatus(StrEnum):
    """Define the persisted editorial-post lifecycle used by PR1."""
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Post:
    """Represent editorial content independently from platform publication."""
    id: object
    knowledge_unit_id: object
    content: str
    status: PostStatus
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    review_note: str | None
