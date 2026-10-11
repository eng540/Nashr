"""Provider-neutral contract for image generation capabilities."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeneratedImage:
    """Validated image bytes returned by any configured image provider."""

    content: bytes
    mime_type: str
    model: str
    provider: str = "unknown"


class ImageGenerator(Protocol):
    """Stable port consumed by the production capability."""

    provider_name: str

    async def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
    ) -> GeneratedImage: ...
