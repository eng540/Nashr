import base64
from types import SimpleNamespace

import pytest

from app.adapters.video_generation.veo import (
    VeoProviderOutcomeUnknownError,
    VeoVideoGenerationError,
    VeoVideoGenerator,
)


def _valid_mp4() -> bytes:
    return bytes([0, 0, 0, 16]) + b"ftypisom" + bytes([0, 0, 0, 0])


class FakeInteractions:
    def __init__(self, interaction=None, created=None):
        self.interaction = interaction or SimpleNamespace(status="in_progress")
        self.created = created or SimpleNamespace(id="v1_interaction-123")
        self.create_calls = []
        self.get_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.created

    def get(self, *, id, timeout=None):
        self.get_calls.append((id, timeout))
        return self.interaction


class FakeClient:
    def __init__(self, interaction=None, created=None):
        self.interactions = FakeInteractions(interaction=interaction, created=created)


@pytest.mark.asyncio
async def test_gemini_omni_start_uses_background_interaction_and_persists_id():
    client = FakeClient()
    generator = VeoVideoGenerator(client=client)

    interaction_id = await generator.start(
        "Create a short literary video",
        aspect_ratio="9:16",
        resolution="720p",
        duration_seconds=5,
    )

    assert interaction_id == "v1_interaction-123"
    call = client.interactions.create_calls[0]
    assert call["model"] == "gemini-omni-1.1-flash"
    assert "Requested target duration: approximately 5 seconds" in call["input"]
    assert call["response_format"] == {
        "type": "video",
        "aspect_ratio": "9:16",
        "resolution": "720p",
    }
    assert call["background"] is True
    assert call["store"] is True


@pytest.mark.asyncio
async def test_gemini_omni_poll_resumes_running_interaction():
    client = FakeClient(SimpleNamespace(status="in_progress"))
    result = await VeoVideoGenerator(client=client).poll("v1_interaction-123")

    assert result.done is False
    assert result.status == "RUNNING"
    assert client.interactions.get_calls == [("v1_interaction-123", 60)]


@pytest.mark.asyncio
async def test_gemini_omni_poll_returns_validated_video_bytes():
    payload = _valid_mp4()
    completed = SimpleNamespace(
        id="v1_interaction-123",
        status="completed",
        model="gemini-omni-1.1-flash",
        output_video=SimpleNamespace(
            data=base64.b64encode(payload).decode("ascii"),
            mime_type="video/mp4",
        ),
    )
    client = FakeClient(completed)
    result = await VeoVideoGenerator(client=client).poll("v1_interaction-123")

    assert result.done is True
    assert result.status == "SUCCEEDED"
    assert result.content == payload
    assert result.mime_type == "video/mp4"
    assert result.model == "gemini-omni-1.1-flash"


@pytest.mark.asyncio
async def test_gemini_omni_poll_rejects_malformed_video_payload():
    completed = SimpleNamespace(
        status="completed",
        output_video=SimpleNamespace(
            data=base64.b64encode(b"not-an-mp4").decode("ascii"),
            mime_type="video/mp4",
        ),
    )
    result = await VeoVideoGenerator(client=FakeClient(completed)).poll("v1_interaction-123")

    assert result.done is True
    assert result.status == "FAILED"
    assert result.content is None


@pytest.mark.asyncio
async def test_gemini_omni_poll_rejects_failed_interaction():
    failed = SimpleNamespace(status="failed", error={"message": "provider failure"})
    result = await VeoVideoGenerator(client=FakeClient(failed)).poll("v1_interaction-123")
    assert result.done is True
    assert result.status == "FAILED"


@pytest.mark.asyncio
async def test_gemini_omni_rejects_invalid_generation_options():
    generator = VeoVideoGenerator(client=FakeClient())
    with pytest.raises(ValueError, match="aspect ratio"):
        await generator.start("Create video", aspect_ratio="7:2")
    with pytest.raises(ValueError, match="resolution"):
        await generator.start("Create video", resolution="8k")


@pytest.mark.asyncio
async def test_gemini_omni_start_timeout_is_classified_as_unknown_outcome():
    class TimeoutInteractions(FakeInteractions):
        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            raise TimeoutError("response timed out after request send")

    client = FakeClient()
    client.interactions = TimeoutInteractions()
    with pytest.raises(VeoProviderOutcomeUnknownError) as caught:
        await VeoVideoGenerator(client=client).start("Create a short literary video")
    assert caught.value.code == "PROVIDER_OUTCOME_UNKNOWN"
    assert "no durable operation ID" in str(caught.value)


@pytest.mark.asyncio
async def test_gemini_omni_start_clear_client_rejection_is_not_unknown():
    class RejectedInteractions(FakeInteractions):
        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            error = RuntimeError("bad request")
            error.status_code = 400
            raise error

    client = FakeClient()
    client.interactions = RejectedInteractions()
    with pytest.raises(VeoVideoGenerationError, match="rejected the video request"):
        await VeoVideoGenerator(client=client).start("Create a short literary video")
