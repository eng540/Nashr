from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True)
class BookTopic:
    """Represent one meaningful navigational topic with evidence-backed page bounds."""
    id: UUID
    source_id: UUID
    position: int
    title: str
    description: str
    source_reference: str | None = None
    page_start: int | None = None
    page_end: int | None = None

    @classmethod
    def create(
        cls,
        source_id: UUID,
        position: int,
        title: str,
        description: str,
        source_reference: str | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
    ) -> "BookTopic":
        return cls(uuid4(), source_id, position, title, description, source_reference, page_start, page_end)


@dataclass(frozen=True)
class BookMap:
    """Represent the practical editorial/navigation map of one book."""
    source_id: UUID
    title: str
    description: str
    topics: list[BookTopic]
