"""Gemini image generation through the centralized generate_content policy."""
import asyncio
import base64
import binascii
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from google.genai import types

from app.adapters.gemini_policy import (
    GEMINI_EMPTY_RESPONSE,
    GeminiOperationError,
    create_gemini_client,
    generate_content as generate_gemini_content,
    parse_model_chain,
)


class GeminiImageGenerationError(GeminiOperationError):
    """Image generation returned an invalid or missing image payload."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(GEMINI_EMPTY_RESPONSE, message, True, cause)


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    mime_type: str
    model: str


def _parts(response: Any) -> Sequence[Any]:
    direct = getattr(response, "parts", None)
    if direct is not None:
        return direct
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ()
    content = getattr(candidates[0], "content", None)
    return getattr(content, "parts", ()) if content is not None else ()


def _image_from_response(response: Any) -> tuple[bytes, str]:
    for part in _parts(response):
        if getattr(part, "thought", False):
            continue
        blob = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
        data = getattr(blob, "data", None) if blob is not None else None
        if not data:
            continue
        if isinstance(data, str):
            try:
                data = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise GeminiImageGenerationError("Gemini returned invalid encoded image bytes.", exc) from exc
        mime_type = getattr(blob, "mime_type", None) or getattr(blob, "mimeType", None) or "image/png"
        if not isinstance(data, bytes) or not data:
            raise GeminiImageGenerationError("Gemini returned an invalid image part.")
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise GeminiImageGenerationError("Gemini returned an unsupported image MIME type.")
        if len(data) > 20 * 1024 * 1024:
            raise GeminiImageGenerationError("Gemini image payload exceeds the 20 MiB limit.")
        return data, str(mime_type)
    raise GeminiImageGenerationError("Gemini returned no image content.")


def _require_image_response(response: Any) -> None:
    _image_from_response(response)


class GeminiImageGenerator:
    """Generate a validated image using the central retry and model-failover policy."""

    def __init__(self, client=None, model: str | None = None) -> None:
        self._client = client
        configured_models = model if model is not None else (os.getenv("GEMINI_IMAGE_MODEL") or "gemini-nano-banana-2.1")
        self.models = parse_model_chain(configured_models)
        self.model = self.models[0]

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

        config = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=image_size),
        )
        response = generate_gemini_content(
            self.client,
            contents=prompt,
            config=config,
            models=self.models,
            operation="image_generation",
            context={"aspect_ratio": aspect_ratio, "image_size": image_size},
            validator=_require_image_response,
        )
        content, mime_type = _image_from_response(response)
        return GeneratedImage(
            content=content,
            mime_type=mime_type,
            model=str(getattr(response, "model_version", None) or self.model),
        )
