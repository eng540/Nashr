from app.domain.extraction import ExtractedIdea, IExtractor
from app.domain.sources import Source


class FakeExtractor(IExtractor):
    """Return deterministic materials without network access."""

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Return deterministic test materials."""
        return [
            ExtractedIdea(position=index, title=f"Mock material {index}", content=f"Mock content {index} from {source.filename}.", original_text=f"Original mock text {index}", source_reference=f"page {index}")
            for index in range(1, 6)
        ]
