from dataclasses import dataclass
from typing import Protocol

from app.domain.sources import Source


@dataclass(frozen=True)
class ExtractedIdea:
    """Represent one structured material discovered in a source."""
    position: int
    title: str
    content: str
    original_text: str | None = None
    source_reference: str | None = None


class IExtractor(Protocol):
    """Define the extraction port used by the application layer."""

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Discover zero or more materials from a source."""
