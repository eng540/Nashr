"""fal.ai image generation adapter implementing Nashr's stable image port."""
import asyncio
import os
from urllib.parse import urlparse

import httpx

from app.application.image_generation import GeneratedImage


class FalImageGenerationError(RuntimeError):
    """fal.ai failed or returned an unusable image."""


_ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_ALLOWED_HOSTS = {"fal.media", "fal.ai", "storage.googleapis.com"}


def _mime_matches(data: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return data.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
    if mime_type == "image/jpeg":
        return len(data) >= 4 and data.startswith(bytes([255, 216, 255])) and data.endswith(bytes([255, 217]))
    if mime_type == "image/webp":
        return (
            len(data) >= 12
            and data[:4] == b"RIFF"
            and int.from_bytes(data[4:8], "little") == len(data) - 8
            and data[8:12] == b"WEBP"
        )
    return False


def _provider_image_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FalImageGenerationError("fal.ai returned no image URL.")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    allowed_host = host in _ALLOWED_HOSTS or any(host.endswith("." + suffix) for suffix in _ALLOWED_HOSTS)
    if parsed.scheme != "https" or not allowed_host or parsed.username or parsed.password:
        raise FalImageGenerationError("fal.ai returned an image URL outside the approved HTTPS hosts.")
    return value


class FalImageGenerator:
    """Generate images through fal.ai while hiding queue and model-specific details."""

    provider_name = "fal"

    def __init__(self, model: str | None = None, *, model_options: dict[str, object] | None = None) -> None:
        self.model = (model or os.getenv("IMAGE_GENERATION_MODEL") or "fal-ai/nano-banana-2").strip()
        if not self.model or len(self.model) > 200 or self.model.startswith("/") or ".." in self.model.split("/"):
            raise ValueError("A valid fal.ai model endpoint ID is required.")
        self.model_options = dict(model_options or {})

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
        if not os.getenv("FAL_KEY", "").strip():
            raise FalImageGenerationError("FAL_KEY is required when the fal image provider is selected.")

        arguments: dict[str, object] = {"prompt": prompt.strip()}
        # Nano Banana endpoints share this documented option set. Other model
        # schemas are intentionally configured through model_options rather than
        # leaking their provider-specific parameters into the application layer.
        if "nano-banana" in self.model:
            arguments.update(
                aspect_ratio=aspect_ratio,
                resolution=image_size,
                output_format="png",
                num_images=1,
            )
        arguments.update(self.model_options)

        try:
            import fal_client

            result = fal_client.subscribe(self.model, arguments=arguments)
        except Exception as exc:
            raise FalImageGenerationError("fal.ai image generation request failed.") from exc

        images = result.get("images") if isinstance(result, dict) else None
        if not isinstance(images, list) or not images or not isinstance(images[0], dict):
            raise FalImageGenerationError("fal.ai returned no image result.")
        image_info = images[0]
        image_url = _provider_image_url(image_info.get("url"))
        declared_mime = str(image_info.get("content_type") or "image/png").split(";", 1)[0].strip().lower()
        if declared_mime not in _ALLOWED_MIME_TYPES:
            raise FalImageGenerationError("fal.ai returned an unsupported image MIME type.")

        chunks: list[bytes] = []
        total = 0
        try:
            with httpx.Client(timeout=60.0, follow_redirects=False) as client:
                with client.stream("GET", image_url) as response:
                    response.raise_for_status()
                    response_mime = response.headers.get("content-type", declared_mime).split(";", 1)[0].strip().lower()
                    if response_mime not in _ALLOWED_MIME_TYPES or response_mime != declared_mime:
                        raise FalImageGenerationError("fal.ai image response MIME type is invalid or inconsistent.")
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > _MAX_IMAGE_BYTES:
                        raise FalImageGenerationError("fal.ai image exceeds the 20 MiB limit.")
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > _MAX_IMAGE_BYTES:
                            raise FalImageGenerationError("fal.ai image exceeds the 20 MiB limit.")
                        chunks.append(chunk)
        except FalImageGenerationError:
            raise
        except Exception as exc:
            raise FalImageGenerationError("Unable to retrieve the generated fal.ai image.") from exc

        content = b"".join(chunks)
        if not content or not _mime_matches(content, declared_mime):
            raise FalImageGenerationError("fal.ai image bytes do not match the declared MIME type.")
        return GeneratedImage(
            content=content,
            mime_type=declared_mime,
            model=self.model,
            provider=self.provider_name,
        )
