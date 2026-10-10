import struct
import zlib
from types import SimpleNamespace

import pytest

from app.adapters.image_generation.gemini import GeminiImageGenerationError, GeminiImageGenerator


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _valid_png_bytes() -> bytes:
    return (
        bytes([137, 80, 78, 71, 13, 10, 26, 10])
        + _png_chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes([0, 255, 0, 0])))
        + _png_chunk(b"IEND", b"")
    )


def _response(data=None, mime_type="image/png"):
    if data is None:
        data = _valid_png_bytes()
    return SimpleNamespace(
        model_version="test-image-model",
        parts=[SimpleNamespace(
            thought=False,
            inline_data=SimpleNamespace(data=data, mime_type=mime_type),
        )],
    )


@pytest.mark.asyncio
async def test_gemini_image_generator_uses_supported_endpoint_and_validates_image():
    client = FakeClient(_response())
    generator = GeminiImageGenerator(client=client, model="test-image-model")

    result = await generator.generate("Make an editorial illustration", aspect_ratio="4:5", image_size="1K")

    assert result.content == _valid_png_bytes()
    assert result.mime_type == "image/png"
    assert result.model == "test-image-model"
    call = client.models.calls[0]
    assert call["model"] == "test-image-model"
    assert call["contents"] == "Make an editorial illustration"
    assert call["config"].response_modalities == ["TEXT", "IMAGE"]
    assert call["config"].image_config.aspect_ratio == "4:5"
    assert call["config"].image_config.image_size == "1K"


@pytest.mark.asyncio
async def test_gemini_image_generator_rejects_missing_or_unsupported_output(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_RETRY_MAX_ATTEMPTS", "1")
    no_image = GeminiImageGenerator(client=FakeClient(SimpleNamespace(parts=[])), model="test-image-model")
    with pytest.raises(GeminiImageGenerationError, match="no image content"):
        await no_image.generate("Create an image")

    unsupported = GeminiImageGenerator(client=FakeClient(_response(b"GIF89a-data", "image/gif")), model="test-image-model")
    with pytest.raises(GeminiImageGenerationError, match="unsupported image MIME"):
        await unsupported.generate("Create an image")


@pytest.mark.asyncio
async def test_gemini_image_generator_rejects_invalid_generation_options():
    generator = GeminiImageGenerator(client=FakeClient(_response()), model="test-image-model")
    with pytest.raises(ValueError, match="aspect ratio"):
        await generator.generate("Create an image", aspect_ratio="7:2")
    with pytest.raises(ValueError, match="Image size"):
        await generator.generate("Create an image", image_size="16K")


@pytest.mark.asyncio
async def test_gemini_image_generator_rejects_bytes_that_do_not_match_declared_mime():
    generator = GeminiImageGenerator(
        client=FakeClient(_response(b"not-a-png", "image/png")),
        model="test-image-model",
    )
    with pytest.raises(GeminiImageGenerationError, match="do not match"):
        await generator.generate("Create an image")


@pytest.mark.asyncio
async def test_gemini_image_generator_rejects_png_with_corrupt_chunk_crc():
    png = bytearray(_valid_png_bytes())
    png[29] ^= 0x01
    generator = GeminiImageGenerator(
        client=FakeClient(_response(bytes(png), "image/png")),
        model="test-image-model",
    )
    with pytest.raises(GeminiImageGenerationError, match="do not match"):
        await generator.generate("Create an image")
