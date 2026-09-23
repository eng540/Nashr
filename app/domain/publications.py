from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class PublicationStatus(StrEnum):
    """Define publication lifecycle states."""
    DRAFT = "DRAFT"
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PublishResult:
    """Represent the result returned by a publisher."""
    external_id: str


class IPublisher(Protocol):
    """Define the platform publishing port."""

    async def publish(self, *, destination: str, content: str) -> PublishResult:
        """Publish content and return its external message identifier."""


@dataclass(frozen=True)
class Publication:
    """Represent a publication ledger entry."""
    id: object
    knowledge_unit_id: object
    platform: str
    destination: str
    content: str
    status: PublicationStatus
    external_id: str | None
    error_message: str | None
    created_at: datetime
    published_at: datetime | None
