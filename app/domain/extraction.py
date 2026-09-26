from dataclasses import dataclass
from typing import Protocol
from app.domain.sources import Source
from app.domain.book_map import BookMap, BookTopic


@dataclass(frozen=True)
class ExtractedIdea:
    """Represent one structured material discovered in a source."""
    position: int
    title: str
    content: str
    original_text: str | None = None
    source_reference: str | None = None
    kind: str | None = None


@dataclass(frozen=True)
class DocumentReference:
    """Represent a reusable external document reference."""
    name: str
    uri: str
    mime_type: str


@dataclass(frozen=True)
class DiscoverySpan:
    """Bounded source span supplied to one Gemini discovery call."""
    page_start: int
    page_end: int
    chunk_index: int = 1


class IExtractor(Protocol):
    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Discover zero or more materials from a source."""


class IBookMapper(Protocol):
    async def prepare_document(self, source: Source) -> DocumentReference:
        """Prepare or reuse the external document representation."""

    async def map_book(self, source: Source, document: DocumentReference) -> BookMap:
        """Understand a book using the prepared document."""


class ITopicMaterialDiscoverer(Protocol):
    async def discover_topic(
        self,
        source: Source,
        topic: BookTopic,
        document: DocumentReference,
        span: DiscoverySpan,
    ) -> list[ExtractedIdea]:
        """Discover zero or more grounded materials inside one bounded source span."""
