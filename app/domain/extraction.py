from dataclasses import dataclass
from typing import Protocol

from app.domain.sources import Source
from app.domain.book_map import BookTopic


@dataclass(frozen=True)
class ExtractedIdea:
    """Represent one structured material discovered in a source."""
    position: int
    title: str
    content: str
    original_text: str | None = None
    source_reference: str | None = None
    kind: str | None = None


class IExtractor(Protocol):
    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Discover zero or more materials from a source."""


class IBookMapper(Protocol):
    async def map_book(self, source: Source):
        """Understand a book and return its navigational map."""


class ITopicMaterialDiscoverer(Protocol):
    async def discover_topic(self, source: Source, topic: BookTopic) -> list[ExtractedIdea]:
        """Discover zero or more grounded materials inside one topic."""
