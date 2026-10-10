import base64
from types import SimpleNamespace

import pytest

from app.adapters.image_generation.gemini import GeminiImageGenerationError, GeminiImageGenerator


class FakeInteractions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.interactions = FakeInteractions(response)


@pytest.mark.asyncio
async def test_gemini_image_generator_returns_validated_image_bytes():
    encoded = base64.b64encode(b"png-bytes").decode("ascii")
    client = FakeClient(SimpleNamespace(
        output_image=SimpleNamespace(data=encoded, mime_type="image/png"),
        steps=[],
    ))
    generator = GeminiImageGenerator(client=client, model="test-image-model")

    result = await generator.generate("Make an editorial illustration", aspect_ratio="4:5", image_size="1K")

    assert result.content == b"png-bytes"
    assert result.mime_type == "image/png"
    assert result.model == "test-image-model"
    assert client.interactions.calls == [{
        "model": "test-image-model",
        "input": "Make an editorial illustration",
        "response_format": {"type": "image", "aspect_ratio": "4:5", "image_size": "1K"},
    }]


@pytest.mark.asyncio
async def test_gemini_image_generator_rejects_missing_or_unsupported_output():
    no_image = GeminiImageGenerator(client=FakeClient(SimpleNamespace(output_image=None, steps=[])))
    with pytest.raises(GeminiImageGenerationError, match="no image data"):
        await no_image.generate("Create an image")

    encoded = base64.b64encode(b"image").decode("ascii")
    unsupported = GeminiImageGenerator(client=FakeClient(SimpleNamespace(
        output_image=SimpleNamespace(data=encoded, mime_type="image/gif"),
        steps=[],
    )))
    with pytest.raises(GeminiImageGenerationError, match="unsupported image MIME"):
        await unsupported.generate("Create an image")


@pytest.mark.asyncio
async def test_gemini_image_generator_rejects_invalid_generation_options():
    generator = GeminiImageGenerator(client=FakeClient(SimpleNamespace(output_image=None, steps=[])))
    with pytest.raises(ValueError, match="aspect ratio"):
        await generator.generate("Create an image", aspect_ratio="7:2")
    with pytest.raises(ValueError, match="image size"):
        await generator.generate("Create an image", image_size="16K")
