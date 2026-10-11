import sys
from types import SimpleNamespace

import pytest

from app.adapters.image_generation import fal as fal_adapter
from app.adapters.image_generation.fal import FalImageGenerator, _mime_matches, _provider_image_url
from app.adapters.image_generation.factory import create_image_generator
from app.adapters.image_generation.gemini import GeminiImageGenerator


def test_factory_uses_environment_default_and_can_select_fal(monkeypatch):
    monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "fal")
    monkeypatch.setenv("IMAGE_GENERATION_MODEL", "fal-ai/flux/schnell")
    generator = create_image_generator()
    assert isinstance(generator, FalImageGenerator)
    assert generator.provider_name == "fal"
    assert generator.model == "fal-ai/flux/schnell"


def test_recipe_stage_can_override_provider_and_model_without_code_changes(monkeypatch):
    monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "gemini")
    generator = create_image_generator({
        "provider": "fal",
        "model": "fal-ai/flux-2-pro",
        "aspect_ratio": "16:9",
        "image_size": "2K",
    })
    assert isinstance(generator, FalImageGenerator)
    assert generator.model == "fal-ai/flux-2-pro"


def test_factory_keeps_gemini_as_supported_alternative(monkeypatch):
    monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "gemini-test-image")
    generator = create_image_generator()
    assert isinstance(generator, GeminiImageGenerator)
    assert generator.model == "gemini-test-image"


def test_factory_rejects_unknown_provider_and_invalid_model_options():
    with pytest.raises(ValueError, match="Unsupported image generation provider"):
        create_image_generator({"provider": "unknown"})


def test_fal_image_url_must_use_approved_https_host():
    assert _provider_image_url("https://v3.fal.media/files/example.png").startswith("https://")
    with pytest.raises(Exception, match="approved HTTPS hosts"):
        _provider_image_url("http://127.0.0.1/private.png")
    with pytest.raises(Exception, match="approved HTTPS hosts"):
        _provider_image_url("https://example.com/image.png")


def test_fal_image_mime_validation_rejects_mismatched_bytes():
    assert _mime_matches(bytes([137, 80, 78, 71, 13, 10, 26, 10]), "image/png")
    assert not _mime_matches(b"not-an-image", "image/png")



def test_flux_schnell_requests_png_to_match_image_artifact_contract(monkeypatch):
    png_bytes = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    captured = {}

    def subscribe(model, *, arguments):
        captured["model"] = model
        captured["arguments"] = arguments
        return {"images": [{
            "url": "https://v3.fal.media/files/example.png",
            "content_type": "image/png",
        }]}

    class FakeResponse:
        headers = {"content-type": "image/png", "content-length": str(len(png_bytes))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self):
            yield png_bytes

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            return FakeResponse()

    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "fal_client", SimpleNamespace(subscribe=subscribe))
    monkeypatch.setattr(fal_adapter.httpx, "Client", FakeClient)

    generated = FalImageGenerator("fal-ai/flux/schnell")._generate_sync(
        "A literary scene", "1:1", "1K"
    )

    assert captured["arguments"]["output_format"] == "png"
    assert generated.mime_type == "image/png"
    assert generated.content == png_bytes
