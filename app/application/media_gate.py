"""Deployment-level kill switch for media generation (image/audio/video).

Set NASHR_MEDIA_GENERATION_DISABLED=true to block every AI media generation
call before any provider spend. Uploading or publishing already-generated
media is unaffected. Text generation is unaffected.
"""
import os


class MediaGenerationDisabledError(RuntimeError):
    """Media generation is disabled on this deployment."""


_TRUTHY = {"1", "true", "yes", "on"}


def media_generation_disabled() -> bool:
    return os.getenv("NASHR_MEDIA_GENERATION_DISABLED", "").strip().lower() in _TRUTHY


def ensure_media_generation_enabled() -> None:
    if media_generation_disabled():
        raise MediaGenerationDisabledError(
            "Media generation is disabled on this deployment (NASHR_MEDIA_GENERATION_DISABLED)."
        )
