"""Gemini image generation through the centralized generate_content policy."""
import asyncio
import base64
import binascii
import os
import zlib
from collections.abc import Sequence
from typing import Any

from app.application.image_generation import GeneratedImage

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


def _parts(response: Any) -> Sequence[Any]:
    direct = getattr(response, "parts", None)
    if direct is not None:
        return direct
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ()
    content = getattr(candidates[0], "content", None)
    return getattr(content, "parts", ()) if content is not None else ()


def _image_bytes_match_mime(data: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        if not data.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10])):
            return False
        cursor = 8
        seen_ihdr = False
        seen_idat = False
        seen_iend = False
        while cursor + 12 <= len(data):
            length = int.from_bytes(data[cursor:cursor + 4], "big")
            kind = data[cursor + 4:cursor + 8]
            data_start = cursor + 8
            data_end = data_start + length
            chunk_end = data_end + 4
            if data_end < data_start or chunk_end > len(data):
                return False
            chunk_data = data[data_start:data_end]
            expected_crc = int.from_bytes(data[data_end:chunk_end], "big")
            if (zlib.crc32(kind + chunk_data) & 0xFFFFFFFF) != expected_crc:
                return False
            if not seen_ihdr:
                if kind != b"IHDR" or length != 13:
                    return False
                if int.from_bytes(chunk_data[:4], "big") < 1 or int.from_bytes(chunk_data[4:8], "big") < 1:
                    return False
                seen_ihdr = True
            elif kind == b"IHDR":
                return False
            if kind == b"IDAT":
                seen_idat = True
            if kind == b"IEND":
                if length != 0:
                    return False
                seen_iend = True
                cursor = chunk_end
                break
            cursor = chunk_end
        return seen_ihdr and seen_idat and seen_iend and cursor == len(data)
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
        if not _image_bytes_match_mime(data, str(mime_type)):
            raise GeminiImageGenerationError("Gemini image bytes do not match the declared image MIME type.")
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
            provider="gemini",
        )
