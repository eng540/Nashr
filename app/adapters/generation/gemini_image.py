import asyncio
import base64
import binascii
import os
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import types

from app.adapters.gemini_policy import (
    GEMINI_EMPTY_RESPONSE,
    GeminiOperationError,
    create_gemini_client,
    generate_content as generate_gemini_content,
    parse_model_chain,
)
from app.domain.image_generation import GeneratedImage, IImageGenerator


DEFAULT_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"


def _parts(response: Any) -> Sequence[Any]:
    direct = getattr(response, "parts", None)
    if direct is not None:
        return direct
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ()
    content = getattr(candidates[0], "content", None)
    return getattr(content, "parts", ()) if content is not None else ()


def _image_from_response(response: Any) -> GeneratedImage:
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
                raise GeminiOperationError(GEMINI_EMPTY_RESPONSE, "Gemini returned invalid encoded image bytes.", True, exc) from exc
        mime_type = getattr(blob, "mime_type", None) or getattr(blob, "mimeType", None) or "image/png"
        try:
            return GeneratedImage(data=bytes(data), mime_type=str(mime_type))
        except (TypeError, ValueError) as exc:
            raise GeminiOperationError(GEMINI_EMPTY_RESPONSE, "Gemini returned an invalid image part.", True, exc) from exc
    raise GeminiOperationError(GEMINI_EMPTY_RESPONSE, "Gemini returned no image content.", True)


def _require_image_response(response: Any) -> None:
    _image_from_response(response)


class GeminiImageGenerator(IImageGenerator):
    """Gemini 3.1 Flash Image adapter using Nashr's shared Gemini retry policy."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        self._client = client
        self.models = parse_model_chain(model or os.getenv("GEMINI_IMAGE_MODEL") or DEFAULT_GEMINI_IMAGE_MODEL)

    @property
    def client(self) -> genai.Client:
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
        if not prompt.strip():
            raise ValueError("Image generation prompt is required.")
        if aspect_ratio not in {"1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}:
            raise ValueError("Unsupported image aspect ratio.")
        if image_size not in {"512", "1K", "2K", "4K"}:
            raise ValueError("Unsupported image size.")
        return await asyncio.to_thread(self._generate_sync, prompt, aspect_ratio, image_size)

    def _generate_sync(self, prompt: str, aspect_ratio: str, image_size: str) -> GeneratedImage:
        response = generate_gemini_content(
            self.client,
            models=self.models,
            operation="IMAGE_GENERATION",
            context={"aspect_ratio": aspect_ratio, "image_size": image_size},
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                response_format={"image": {"aspect_ratio": aspect_ratio, "image_size": image_size}},
            ),
            validator=_require_image_response,
        )
        return _image_from_response(response)
