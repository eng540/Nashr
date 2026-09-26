from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import DocumentReference, ExtractedIdea, IBookMapper, IExtractor, ITopicMaterialDiscoverer
from app.domain.sources import Source


class FakeExtractor(IExtractor):
    def __init__(self, count: int = 5) -> None:
        self.count = count

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        return [
            ExtractedIdea(
                position=i,
                title=f"Mock material {i}",
                content=f"Mock content {i} from {source.filename}.",
                original_text=f"Original mock text {i}",
                source_reference=f"page {i}",
                kind="mock",
            )
            for i in range(1, self.count + 1)
        ]


class FakeBookMapper(IBookMapper):
    async def prepare_document(self, source: Source) -> DocumentReference:
        return DocumentReference("fake-document", "fake://document", "application/pdf")

    async def map_book(self, source: Source, document: DocumentReference) -> BookMap:
        topic = BookTopic.create(source.id, 1, "Mock topic", "A deterministic test topic.", "page 1")
        return BookMap(source.id, source.filename, "Mock book description.", [topic])


class FakeTopicMaterialDiscoverer(ITopicMaterialDiscoverer):
    def __init__(self, count: int = 6) -> None:
        self.count = count

    async def discover_topic(self, source: Source, topic: BookTopic, document: DocumentReference) -> list[ExtractedIdea]:
        return [
            ExtractedIdea(
                position=i,
                title=f"Topic material {i}",
                content=f"Topic content {i}",
                original_text=f"Original topic text {i}",
                source_reference=f"page {i}",
                kind=("حكمة" if i == 1 else "نوع مكتشف"),
            )
            for i in range(1, self.count + 1)
        ]
