from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True)
class BookTopic:
    """Represent one meaningful navigational topic discovered in a book."""
    id: UUID
    source_id: UUID
    position: int
    title: str
    description: str
    source_reference: str | None = None

    @classmethod
    def create(cls, source_id: UUID, position: int, title: str, description: str, source_reference: str | None = None) -> "BookTopic":
        return cls(uuid4(), source_id, position, title, description, source_reference)


@dataclass(frozen=True)
class BookMap:
    """Represent the practical editorial/navigation map of one book."""
    source_id: UUID
    title: str
    description: str
    topics: list[BookTopic]
