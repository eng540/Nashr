"""Gemini Omni video generation adapter with durable interaction handles."""
import asyncio
import base64
import binascii
import os
from dataclasses import dataclass


class VeoVideoGenerationError(RuntimeError):
    """Video generation failed or returned an invalid payload."""


@dataclass(frozen=True)
class VideoOperationResult:
    operation_name: str
    done: bool
    status: str
    content: bytes | None = None
    mime_type: str | None = None
    model: str | None = None
    error_message: str | None = None


def _valid_mp4(data: bytes) -> bool:
    if len(data) < 12 or data[4:8] != b"ftyp":
        return False
    box_size = int.from_bytes(data[:4], "big")
    return 8 <= box_size <= len(data)


class VeoVideoGenerator:
    """Compatibility-named adapter using Gemini Omni's durable Interactions API.

    The old Veo preview endpoint is being retired; this adapter preserves Nashr's
    persisted operation-handle contract while using the supported Omni model/API.
    """

    provider_name = "google-gemini-omni"

    def __init__(self, client=None, model: str | None = None) -> None:
        self._client = client
        self.model = model or os.getenv("GEMINI_VIDEO_MODEL", "gemini-omni-1.1-flash")

    @property
    def client(self):
        if self._client is None:
            from app.adapters.gemini_policy import create_gemini_client
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
            raise ValueError("Gemini Omni aspect ratio must be 16:9 or 9:16.")
        if resolution not in {"360p", "720p", "1080p", "4k"}:
            raise ValueError("Gemini Omni resolution must be 360p, 720p, 1080p, or 4k.")
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or duration_seconds not in {4, 5, 6, 8}:
            raise ValueError("Requested video duration must be 4, 5, 6, or 8 seconds.")
        requested_prompt = (
            f"{prompt.strip()}\n\nRequested target duration: approximately {duration_seconds} seconds. "
            "Prioritize a coherent single shot."
        )
        interaction = self.client.interactions.create(
            model=self.model,
            input=requested_prompt,
            response_format={
                "type": "video",
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
            },
            background=True,
            store=True,
            timeout=120,
        )
        interaction_id = getattr(interaction, "id", None)
        if not isinstance(interaction_id, str) or not interaction_id.strip():
            raise VeoVideoGenerationError("Gemini Omni did not return a durable interaction ID.")
        return interaction_id

    async def poll(self, operation_name: str) -> VideoOperationResult:
        if not isinstance(operation_name, str) or not operation_name.strip():
            raise ValueError("Video interaction ID is required.")
        return await asyncio.to_thread(self._poll_sync, operation_name)

    def _poll_sync(self, operation_name: str) -> VideoOperationResult:
        interaction = self.client.interactions.get(id=operation_name, timeout=60)
        status = str(getattr(interaction, "status", "") or "").lower()
        if status in {"in_progress", "running", "queued", "pending"}:
            return VideoOperationResult(
                operation_name=operation_name,
                done=False,
                status="RUNNING",
                model=self.model,
            )
        if status in {"failed", "cancelled", "canceled", "incomplete"} or getattr(interaction, "error", None):
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Gemini Omni video interaction failed or was cancelled.",
            )
        output = getattr(interaction, "output_video", None)
        encoded = getattr(output, "data", None) if output is not None else None
        mime_type = getattr(output, "mime_type", None) if output is not None else None
        if isinstance(encoded, bytes):
            try:
                encoded = encoded.decode("ascii")
            except UnicodeDecodeError:
                encoded = None
        if not isinstance(encoded, str) or not encoded:
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Gemini Omni completed without inline video data.",
            )
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            content = b""
        if mime_type != "video/mp4" or not _valid_mp4(content) or len(content) > 100 * 1024 * 1024:
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Gemini Omni returned an invalid or unsupported video payload.",
            )
        if status not in {"completed", "succeeded", "success"}:
            return VideoOperationResult(
                operation_name=operation_name,
                done=True,
                status="FAILED",
                model=self.model,
                error_message="Gemini Omni interaction ended without a successful completion status.",
            )
        return VideoOperationResult(
            operation_name=operation_name,
            done=True,
            status="SUCCEEDED",
            content=content,
            mime_type=mime_type,
            model=str(getattr(interaction, "model", None) or self.model),
        )
