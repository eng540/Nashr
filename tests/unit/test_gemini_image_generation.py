from types import SimpleNamespace

import pytest

from app.adapters.generation.gemini_image import GeminiImageGenerator


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)


@pytest.mark.asyncio
async def test_gemini_image_generator_uses_shared_client_policy_and_returns_image_bytes():
    response = SimpleNamespace(parts=[
        SimpleNamespace(inline_data=SimpleNamespace(data=b"png-bytes", mime_type="image/png"), thought=False)
    ])
    client = FakeClient(response)
    generator = GeminiImageGenerator(client=client, model="test-image-model")

    result = await generator.generate("Create an editorial cover image", aspect_ratio="16:9", image_size="1K")

    assert result.data == b"png-bytes"
    assert result.mime_type == "image/png"
    assert client.models.kwargs["model"] == "test-image-model"
    config = client.models.kwargs["config"]
    assert config.response_modalities == ["TEXT", "IMAGE"]
    assert config.image_config.aspect_ratio == "16:9"
    assert config.image_config.image_size == "1K"


@pytest.mark.asyncio
async def test_gemini_image_generator_decodes_base64_inline_image():
    import base64

    response = SimpleNamespace(parts=[
        SimpleNamespace(
            inline_data=SimpleNamespace(data=base64.b64encode(b"image-bytes").decode("ascii"), mime_type="image/png"),
            thought=False,
        )
    ])
    result = await GeminiImageGenerator(client=FakeClient(response), model="test-image-model").generate("Image prompt")
    assert result.data == b"image-bytes"


@pytest.mark.asyncio
async def test_gemini_image_generator_rejects_empty_prompt():
    generator = GeminiImageGenerator(client=FakeClient(SimpleNamespace(parts=[])), model="test-image-model")
    with pytest.raises(ValueError, match="prompt is required"):
        await generator.generate("   ")
