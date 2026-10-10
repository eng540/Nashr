"""Gemini-native image generation adapter using the Interactions API."""
import asyncio
import base64
import binascii
import os
from dataclasses import dataclass

from app.adapters.gemini_policy import create_gemini_client


class GeminiImageGenerationError(RuntimeError):
    """Image generation failed or returned an invalid image payload."""


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    mime_type: str
    model: str


class GeminiImageGenerator:
    """Generate an image with Gemini and return validated bytes, not a storage concern."""

    def __init__(self, client=None, model: str | None = None) -> None:
        self._client = client
        self.model = model or os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")

    @property
    def client(self):
        if self._client is None:
            self._client = create_gemini_client(api_key=os.getenv("GEMINI_API_KEY"))
        return self._client

    async def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "1:1",
        image_size: str = "1K",
    ) -> GeneratedImage:
        return await asyncio.to_thread(self._generate_sync, prompt, aspect_ratio, image_size)

    def _generate_sync(self, prompt: str, aspect_ratio: str, image_size: str) -> GeneratedImage:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Image generation prompt is required.")
        if aspect_ratio not in {"1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "21:9"}:
            raise ValueError("Unsupported image aspect ratio.")
        if image_size not in {"1K", "2K", "4K"}:
            raise ValueError("Image size must be 1K, 2K, or 4K.")

        try:
            interaction = self.client.interactions.create(
                model=self.model,
                input=prompt,
                response_format={
                    "type": "image",
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,
                },
            )
        except Exception as exc:
            raise GeminiImageGenerationError("Gemini image generation request failed.") from exc

        image = getattr(interaction, "output_image", None)
        if image is None:
            for step in getattr(interaction, "steps", ()) or ():
                if getattr(step, "type", None) != "model_output":
                    continue
                for block in getattr(step, "content", ()) or ():
                    if getattr(block, "type", None) == "image":
                        image = block
        encoded = getattr(image, "data", None) if image is not None else None
        mime_type = getattr(image, "mime_type", None) if image is not None else None
        if isinstance(encoded, bytes):
            try:
                encoded = encoded.decode("ascii")
            except UnicodeDecodeError as exc:
                raise GeminiImageGenerationError("Gemini returned malformed image data.") from exc
        if not isinstance(encoded, str) or not encoded:
            raise GeminiImageGenerationError("Gemini returned no image data.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise GeminiImageGenerationError("Gemini returned malformed image data.") from exc
        if not content or len(content) > 20 * 1024 * 1024:
            raise GeminiImageGenerationError("Gemini image payload is empty or exceeds the 20 MiB limit.")
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise GeminiImageGenerationError("Gemini returned an unsupported image MIME type.")
        return GeneratedImage(content=content, mime_type=mime_type, model=self.model)
