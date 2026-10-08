import asyncio
import logging
import os

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.adapters.gemini_policy import (
    DEFAULT_GEMINI_MODELS,
    DEFAULT_RETRY_BACKOFF_MIN_SECONDS,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    GEMINI_EMPTY_RESPONSE,
    GeminiOperationError,
    create_gemini_client,
    generate_content as generate_gemini_content,
    is_transient_error,
    parse_model_chain,
)
from app.domain.editorial import IEditorialDrafter

logger = logging.getLogger(__name__)

# Backward-compatible views of the values that now live in the central policy.
# The cascade default, the attempts-per-model and the base delay are defined once
# in app/adapters/gemini_policy.py and consumed from there by every layer.
DEFAULT_MODEL_CASCADE = list(DEFAULT_GEMINI_MODELS)
ATTEMPTS_PER_MODEL = DEFAULT_RETRY_MAX_ATTEMPTS
BASE_DELAY_SECONDS = DEFAULT_RETRY_BACKOFF_MIN_SECONDS


class GeminiTelegramDraft(BaseModel):
    """Define the structured Gemini response for a Telegram draft."""

    content: str


# Backward-compatible alias; classification itself lives only in the central policy.
_is_transient_error = is_transient_error


def _require_editorial_draft(response) -> None:
    """Treat an empty model response as a transient failure eligible for failover."""
    parsed = getattr(response, "parsed", None)

    if parsed is None or not (getattr(parsed, "content", "") or "").strip():
        raise GeminiOperationError(
            GEMINI_EMPTY_RESPONSE,
            "Gemini returned no editorial draft.",
            True,
        )


class GeminiEditorialDrafter(IEditorialDrafter):
    """
    Produce publication-ready content from one supplied literary or heritage
    source material.

    This layer is intentionally limited to the material supplied in the
    current request. It does not assume access to the complete source book
    or to other materials.

    The model must first understand the material, identify its actual value,
    determine whether intervention is useful, select the appropriate editorial
    treatment, choose the form, produce the result, and review it before
    returning it.
    """

    def __init__(
        self,
        client: genai.Client | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize with a prioritized cascade of models."""
        if system_prompt is not None:
            raise ValueError("Editorial prompt must be resolved by the application runtime.")
        self._client = client
        self._configured_system_prompt = system_prompt

        raw_models = model or os.getenv("GEMINI_MODEL", "")
        self.model = raw_models
        self.models = list(parse_model_chain(raw_models))

        logger.info(
            "event=DRAFT_CASCADE_CONFIGURED models=%s",
            self.models,
        )

    @property
    def client(self) -> genai.Client:
        """Create the Gemini client only when a real draft is requested."""
        if self._client is None:
            self._client = create_gemini_client(
                api_key=os.getenv("GEMINI_API_KEY")
            )

        return self._client

    async def draft(
        self,
        *,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Generate the editorial result without blocking the event loop."""
        return await asyncio.to_thread(
            self._draft_sync,
            title,
            content,
            source_name,
            pdf_slice,
            system_prompt,
        )

    def _draft_sync(
        self,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        Run the blocking request.

        The application supplies the source metadata and the single material.
        Editorial judgment and form selection remain inside the editorial
        instruction layer.
        """

        if not system_prompt or not system_prompt.strip():
            raise ValueError("Resolved editorial prompt is required.")

        prompt = (
            f"اسم المصدر: {source_name}\n"
            f"عنوان/موضوع المادة: {title}\n"
            f"\n"
            f"المادة المصدرية:\n"
            f"{content}\n"
        )

        contents: list[object] = [
            system_prompt,
            prompt,
        ]

        if pdf_slice:
            contents.append(
                types.Part.from_bytes(
                    data=pdf_slice,
                    mime_type="application/pdf",
                )
            )
            contents.append(
                "الشريحة/الصفحة المرفقة أعلاه جزء من المادة المصدرية نفسها. "
                "اقرأها بعناية، واستخرج منها ما يخدم المادة، "
                "مع الالتزام الصارم بقواعد أمانة المصدر."
            )

        response = generate_gemini_content(
            self.client,
            models=self.models,
            operation="EDITORIAL_DRAFT",
            context={
                "source_name": source_name,
            },
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiTelegramDraft,
            ),
            validator=_require_editorial_draft,
        )

        parsed = response.parsed

        if parsed is None or not parsed.content.strip():
            raise ValueError("Gemini returned no editorial draft.")

        return parsed.content.strip()