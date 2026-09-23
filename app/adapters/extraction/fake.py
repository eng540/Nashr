from app.domain.extraction import ExtractedIdea, IExtractor
from app.domain.sources import Source


class FakeExtractor(IExtractor):
    """Return deterministic ideas without network access."""

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Return exactly five deterministic test ideas."""
        return [
            ExtractedIdea(position=index, title=f"Mock idea {index}", content=f"Mock content {index} from {source.filename}.")
            for index in range(1, 6)
        ]
