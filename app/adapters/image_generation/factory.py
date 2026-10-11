"""Composition boundary for selecting an image provider and model."""
import os
from collections.abc import Mapping

from app.adapters.image_generation.fal import FalImageGenerator
from app.adapters.image_generation.gemini import GeminiImageGenerator


def create_image_generator(stage_configuration: Mapping[str, object] | None = None):
    """Resolve provider/model from pinned recipe configuration, then environment.

    Recipe configuration wins so a production run can pin its provider and model.
    Environment variables provide the deployment-wide default and allow an
    operator to switch providers without changing application code.
    """
    configuration = stage_configuration or {}
    raw_provider = configuration.get("provider", os.getenv("IMAGE_GENERATION_PROVIDER", "gemini"))
    if not isinstance(raw_provider, str):
        raise ValueError("Image provider must be a string.")
    provider = raw_provider.strip().lower()

    raw_model = configuration.get("model")
    model = raw_model.strip() if isinstance(raw_model, str) and raw_model.strip() else None
    if provider == "fal":
        return FalImageGenerator(model=model or os.getenv("IMAGE_GENERATION_MODEL"))
    if provider == "gemini":
        return GeminiImageGenerator(model=model or os.getenv("GEMINI_IMAGE_MODEL"))
    raise ValueError(f"Unsupported image generation provider: {provider!r}. Supported providers: gemini, fal.")
