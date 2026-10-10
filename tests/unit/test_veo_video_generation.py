from pathlib import Path
from types import SimpleNamespace

import pytest

from app.adapters.video_generation.veo import VeoVideoGenerator


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_videos(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(name="operations/veo-123")


class FakeOperations:
    def __init__(self, operation):
        self.operation = operation
        self.calls = []

    def get(self, operation):
        self.calls.append(operation.name)
        return self.operation


class FakeFiles:
    def __init__(self, payload=None):
        self.payload = payload or (bytes([0, 0, 0, 16]) + b"ftypisom" + bytes([0, 0, 0, 0]))

    def download(self, *, file, destination):
        Path(destination).write_bytes(self.payload)


class FakeClient:
    def __init__(self, operation=None, video_payload=None):
        self.models = FakeModels()
        self.operations = FakeOperations(operation or SimpleNamespace(done=False))
        self.files = FakeFiles(video_payload)


@pytest.mark.asyncio
async def test_veo_start_returns_durable_operation_name_and_bounded_config():
    client = FakeClient()
    generator = VeoVideoGenerator(client=client, model="test-veo")

    name = await generator.start(
        "Create a short literary video", aspect_ratio="9:16", resolution="720p", duration_seconds=5
    )

    assert name == "operations/veo-123"
    call = client.models.calls[0]
    assert call["model"] == "test-veo"
    assert call["prompt"] == "Create a short literary video"
    assert call["config"].aspect_ratio == "9:16"
    assert call["config"].resolution == "720p"
    assert call["config"].duration_seconds == 5


@pytest.mark.asyncio
async def test_veo_poll_resumes_pending_operation_and_downloads_completed_video():
    pending_client = FakeClient(SimpleNamespace(done=False))
    pending = await VeoVideoGenerator(client=pending_client).poll("operations/veo-123")
    assert pending.done is False
    assert pending.status == "RUNNING"

    video = SimpleNamespace(uri="https://provider.example/video")
    completed = SimpleNamespace(
        done=True,
        error=None,
        response=SimpleNamespace(generated_videos=[SimpleNamespace(video=video)]),
    )
    complete_client = FakeClient(completed)
    result = await VeoVideoGenerator(client=complete_client, model="test-veo").poll("operations/veo-123")

    assert result.done is True
    assert result.status == "SUCCEEDED"
    assert result.content == bytes([0, 0, 0, 16]) + b"ftypisom" + bytes([0, 0, 0, 0])
    assert result.mime_type == "video/mp4"
    assert result.model == "test-veo"
    assert complete_client.operations.calls == ["operations/veo-123"]



@pytest.mark.asyncio
async def test_veo_legacy_model_id_is_normalized_to_documented_gemini_api_id(monkeypatch):
    monkeypatch.setenv("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-001")
    client = FakeClient()
    generator = VeoVideoGenerator(client=client)

    assert generator.model == "veo-3.1-fast-generate-preview"
    await generator.start("A short video")
    assert client.models.calls[0]["model"] == "veo-3.1-fast-generate-preview"


def test_veo_explicit_legacy_model_id_is_normalized():
    generator = VeoVideoGenerator(client=FakeClient(), model="veo-3.1-fast-generate-001")
    assert generator.model == "veo-3.1-fast-generate-preview"



@pytest.mark.asyncio
async def test_veo_poll_rejects_non_mp4_payload():
    video = SimpleNamespace(uri="https://provider.example/video")
    completed = SimpleNamespace(
        done=True,
        error=None,
        response=SimpleNamespace(generated_videos=[SimpleNamespace(video=video)]),
    )
    client = FakeClient(completed, video_payload=b"not-an-mp4")
    result = await VeoVideoGenerator(client=client, model="test-veo").poll("operations/veo-123")

    assert result.done is True
    assert result.status == "FAILED"
    assert result.content is None
    assert result.error_message == "Veo returned a payload that is not a valid MP4 container."
