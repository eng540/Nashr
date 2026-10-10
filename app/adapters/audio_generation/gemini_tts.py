"""Gemini TTS adapter for source-grounded audio Artifact generation."""
import asyncio
import base64
import binascii
import os
from dataclasses import dataclass

from app.adapters.gemini_policy import create_gemini_client


class GeminiAudioGenerationError(RuntimeError):
    """Audio generation failed or returned an invalid payload."""


@dataclass(frozen=True)
class GeneratedAudio:
    content: bytes
    mime_type: str
    model: str


class GeminiAudioGenerator:
    def __init__(self, client=None, model: str | None = None) -> None:
        self._client = client
        self.model = model or os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")

    @property
    def client(self):
        if self._client is None:
            self._client = create_gemini_client(api_key=os.getenv("GEMINI_API_KEY"))
        return self._client

    async def generate(self, text: str, *, voice: str = "Kore", style: str = "clear, warm literary narration") -> GeneratedAudio:
        return await asyncio.to_thread(self._generate_sync, text, voice, style)

    def _generate_sync(self, text: str, voice: str, style: str) -> GeneratedAudio:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Audio transcript is required.")
        if len(text) > 20000:
            raise ValueError("Audio transcript exceeds the 20000-character limit.")
        if not isinstance(voice, str) or not voice.strip() or len(voice) > 50:
            raise ValueError("A valid TTS voice is required.")
        if not isinstance(style, str) or not style.strip() or len(style) > 500:
            raise ValueError("A valid TTS speech style is required.")
        try:
            interaction = self.client.interactions.create(
                model=self.model,
                input=[{
                    "type": "user_input",
                    "content": [{
                        "type": "text",
                        "text": text,
                        "annotations": [{"type": "speech_metadata", "style": style}],
                    }],
                }],
                response_format={"type": "audio", "mime_type": "audio/wav"},
                generation_config={"speech_config": [{"voice": voice}]},
            )
        except Exception as exc:
            raise GeminiAudioGenerationError("Gemini TTS request failed.") from exc

        audio = getattr(interaction, "output_audio", None)
        encoded = getattr(audio, "data", None) if audio is not None else None
        mime_type = getattr(audio, "mime_type", None) if audio is not None else None
        if isinstance(encoded, bytes):
            try:
                encoded = encoded.decode("ascii")
            except UnicodeDecodeError as exc:
                raise GeminiAudioGenerationError("Gemini returned malformed audio data.") from exc
        if not isinstance(encoded, str) or not encoded:
            raise GeminiAudioGenerationError("Gemini returned no audio data.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise GeminiAudioGenerationError("Gemini returned malformed audio data.") from exc
        if not content or len(content) > 100 * 1024 * 1024:
            raise GeminiAudioGenerationError("Gemini audio payload is empty or exceeds the 100 MiB limit.")
        normalized_mime = mime_type or "audio/wav"
        if normalized_mime != "audio/wav":
            raise GeminiAudioGenerationError("Gemini returned an unsupported audio MIME type.")
        return GeneratedAudio(content=content, mime_type=normalized_mime, model=self.model)
