from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime_type: str

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError("Generated image bytes cannot be empty.")
        if not self.mime_type.startswith("image/"):
            raise ValueError("Generated image MIME type must be an image type.")


class IImageGenerator(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
    ) -> GeneratedImage:
        """Generate one image from a prompt."""
