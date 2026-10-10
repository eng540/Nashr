"""Veo long-running video generation adapter with resumable operation handles."""
import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from google.genai import types

from app.adapters.gemini_policy import create_gemini_client


class VeoVideoGenerationError(RuntimeError):
    """Veo completed an operation with an unusable video result."""


@dataclass(frozen=True)
class VideoOperationResult:
    operation_name: str
    done: bool
    status: str
    content: bytes | None = None
    mime_type: str | None = None
    model: str | None = None
    error_message: str | None = None


class VeoVideoGenerator:
    """Start and poll Veo operations; persistence of operation handles belongs to the application layer."""

    provider_name = "google-veo"

    def __init__(self, client=None, model: str | None = None) -> None:
        self._client = client
        self.model = model or os.getenv("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-001")

    @property
    def client(self):
        if self._client is None:
            self._client = create_gemini_client(api_key=os.getenv("GEMINI_API_KEY"))
        return self._client

    async def start(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        duration_seconds: int = 5,
    ) -> str:
        return await asyncio.to_thread(
            self._start_sync, prompt, aspect_ratio, resolution, duration_seconds
        )

    def _start_sync(self, prompt: str, aspect_ratio: str, resolution: str, duration_seconds: int) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Video generation prompt is required.")
        if aspect_ratio not in {"16:9", "9:16"}:
            raise ValueError("Veo aspect ratio must be 16:9 or 9:16.")
        if resolution not in {"720p", "1080p"}:
            raise ValueError("Veo resolution must be 720p or 1080p.")
        if isinstance(duration_seconds, bool) or duration_seconds not in {5, 6, 8}:
            raise ValueError("Veo duration must be 5, 6, or 8 seconds.")
        operation = self.client.models.generate_videos(
            model=self.model,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                duration_seconds=duration_seconds,
                number_of_videos=1,
            ),
        )
        name = getattr(operation, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise VeoVideoGenerationError("Veo did not return a durable operation name.")
        return name

    async def poll(self, operation_name: str) -> VideoOperationResult:
        if not isinstance(operation_name, str) or not operation_name.strip():
            raise ValueError("Veo operation name is required.")
        return await asyncio.to_thread(self._poll_sync, operation_name)

    def _poll_sync(self, operation_name: str) -> VideoOperationResult:
        operation = self.client.operations.get(types.GenerateVideosOperation(name=operation_name))
        if not getattr(operation, "done", False):
            return VideoOperationResult(
                operation_name=operation_name,
                done=False,
                status="RUNNING",
                model=self.model,
            )
        error = getattr(operation, "error", None)
        if error:
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Veo video generation operation failed.",
            )
        response = getattr(operation, "response", None)
        videos = getattr(response, "generated_videos", None) if response is not None else None
        if not videos:
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Veo completed without returning a video.",
            )
        video = getattr(videos[0], "video", None)
        if video is None:
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Veo completed without a downloadable video.",
            )
        handle, path = tempfile.mkstemp(prefix="nashr-veo-", suffix=".mp4")
        os.close(handle)
        try:
            self.client.files.download(file=video, destination=path)
            content = Path(path).read_bytes()
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        if not content or len(content) > 100 * 1024 * 1024:
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Veo video payload is empty or exceeds the 100 MiB limit.",
            )
        return VideoOperationResult(
            operation_name=operation_name,
            done=True,
            status="SUCCEEDED",
            content=content,
            mime_type="video/mp4",
            model=self.model,
        )
