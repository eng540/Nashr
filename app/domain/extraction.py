from dataclasses import dataclass
from typing import Protocol

from app.domain.sources import Source


@dataclass(frozen=True)
class ExtractedIdea:
    """Represent one structured idea extracted from a source."""
    position: int
    title: str
    content: str


class IExtractor(Protocol):
    """Define the extraction port used by the application layer."""

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Extract exactly five ideas from a source."""
