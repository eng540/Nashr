import base64
from types import SimpleNamespace

import pytest

from app.adapters.audio_generation.gemini_tts import GeminiAudioGenerationError, GeminiAudioGenerator


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
async def test_gemini_tts_returns_validated_wav_bytes():
    encoded = base64.b64encode(b"wav-data").decode("ascii")
    client = FakeClient(SimpleNamespace(output_audio=SimpleNamespace(data=encoded, mime_type="audio/wav")))
    generator = GeminiAudioGenerator(client=client, model="test-tts")

    result = await generator.generate("نص أدبي للإلقاء", voice="Kore", style="warm narration")

    assert result.content == b"wav-data"
    assert result.mime_type == "audio/wav"
    assert result.model == "test-tts"
    call = client.interactions.calls[0]
    assert call["model"] == "test-tts"
    assert call["input"][0]["content"][0]["text"] == "نص أدبي للإلقاء"
    assert call["input"][0]["content"][0]["annotations"] == [
        {"type": "speech_metadata", "style": "warm narration"}
    ]
    assert call["response_format"] == {"type": "audio", "mime_type": "audio/wav"}
    assert call["generation_config"] == {"speech_config": [{"voice": "Kore"}]}


@pytest.mark.asyncio
async def test_gemini_tts_rejects_missing_audio_and_invalid_text():
    generator = GeminiAudioGenerator(client=FakeClient(SimpleNamespace(output_audio=None)))
    with pytest.raises(GeminiAudioGenerationError, match="no audio data"):
        await generator.generate("Valid transcript")
    with pytest.raises(ValueError, match="transcript"):
        await generator.generate("")


@pytest.mark.asyncio
async def test_gemini_tts_rejects_unsupported_audio_mime_type():
    encoded = base64.b64encode(b"pcm-data").decode("ascii")
    generator = GeminiAudioGenerator(client=FakeClient(
        SimpleNamespace(output_audio=SimpleNamespace(data=encoded, mime_type="audio/l16"))
    ))
    with pytest.raises(GeminiAudioGenerationError, match="unsupported audio MIME"):
        await generator.generate("Valid transcript")
