import asyncio
import logging
import os
from collections.abc import Sequence

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
from app.domain.editorial import EditorialSourceMaterial, IEditorialDrafter
from app.application.provider_errors import raise_if_provider_outcome_unknown

logger = logging.getLogger(__name__)

# Backward-compatible views of the values that now live in the central policy.
DEFAULT_MODEL_CASCADE = list(DEFAULT_GEMINI_MODELS)
ATTEMPTS_PER_MODEL = DEFAULT_RETRY_MAX_ATTEMPTS
BASE_DELAY_SECONDS = DEFAULT_RETRY_BACKOFF_MIN_SECONDS


class GeminiTelegramDraft(BaseModel):
    """Define the structured Gemini response for a Telegram draft."""

    content: str


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
    """Produce publication-ready content from explicitly supplied source material."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        self._client = client
        raw_models = model or os.getenv("GEMINI_MODEL", "")
        self.model = raw_models
        self.models = list(parse_model_chain(raw_models))
        logger.info("event=DRAFT_CASCADE_CONFIGURED models=%s", self.models)

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = create_gemini_client(api_key=os.getenv("GEMINI_API_KEY"))
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
        return await asyncio.to_thread(
            self._draft_sync, title, content, source_name, pdf_slice, system_prompt
        )

    async def draft_sources(
        self,
        *,
        theme: str,
        sources: Sequence[EditorialSourceMaterial],
        system_prompt: str,
    ) -> str:
        """Synthesize only the selected materials, preserving visible provenance in context."""
        normalized_theme = theme.strip()
        selected = tuple(sources)
        if not normalized_theme:
            raise ValueError("A thematic composition requires a non-empty theme.")
        if len(selected) < 2:
            raise ValueError("A thematic composition requires at least two selected source materials.")
        if not system_prompt or not system_prompt.strip():
            raise ValueError("Resolved editorial prompt is required.")
        seen_ids: set[str] = set()
        for source in selected:
            if not source.knowledge_unit_id.strip():
                raise ValueError("Every source material must have a knowledge unit identifier.")
            if source.knowledge_unit_id in seen_ids:
                raise ValueError("Selected source materials must not contain duplicate identifiers.")
            seen_ids.add(source.knowledge_unit_id)
            if not source.title.strip() or not source.source_name.strip() or not source.content.strip():
                raise ValueError("Every selected source must have a title, source name, and non-empty content.")
        return await asyncio.to_thread(
            self._draft_sources_sync, normalized_theme, selected, system_prompt
        )

    def _draft_sources_sync(
        self,
        theme: str,
        sources: Sequence[EditorialSourceMaterial],
        system_prompt: str,
    ) -> str:
        source_sections = []
        for index, source in enumerate(sources, start=1):
            reference = source.source_reference or "لا توجد إحالة صفحات محفوظة لهذه المادة"
            source_sections.append(
                f"[المصدر {index}]\n"
                f"معرّف المادة: {source.knowledge_unit_id}\n"
                f"اسم الكتاب/المصدر: {source.source_name}\n"
                f"عنوان المادة: {source.title}\n"
                f"الإحالة المحفوظة: {reference}\n"
                f"النص الأصلي للمادة:\n{source.content}"
            )
        prompt = (
            "مهمة تركيب موضوعي من مواد محددة اختارها المستخدم.\n"
            f"الثيمة المطلوبة: {theme}\n\n"
            "المواد التالية هي مجموعة المصادر الوحيدة المتاحة لهذه المهمة. "
            "لا تخترع نصوصاً أو صفحات أو أسماء مؤلفين، ولا تنسب قولاً إلى مصدر "
            "إلا إذا كان ذلك مدعوماً بالمادة وإحالتها المحفوظة. ميّز بين الاقتباس "
            "الحرفي والتركيب التحريري، ولا تعرض إحالة غير متوفرة على أنها حقيقة.\n\n"
            + "\n\n".join(source_sections)
        )
        try:
            response = generate_gemini_content(
                self.client,
                models=self.models,
                operation="EDITORIAL_MULTI_SOURCE_DRAFT",
                context={"theme": theme, "source_count": len(sources)},
                contents=[system_prompt, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiTelegramDraft,
                ),
                validator=_require_editorial_draft,
            )
        except Exception as exc:
            raise_if_provider_outcome_unknown(exc, provider="Gemini multi-source editorial drafting")
            raise
        parsed = response.parsed
        if parsed is None or not parsed.content.strip():
            raise ValueError("Gemini returned no thematic composition.")
        return parsed.content.strip()

    def _draft_sync(
        self,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
        system_prompt: str | None = None,
    ) -> str:
        if not system_prompt or not system_prompt.strip():
            raise ValueError("Resolved editorial prompt is required.")
        prompt = (
            f"اسم المصدر: {source_name}\n"
            f"عنوان/موضوع المادة: {title}\n\n"
            f"المادة المصدرية:\n{content}\n"
        )
        contents: list[object] = [system_prompt, prompt]
        if pdf_slice:
            contents.append(types.Part.from_bytes(data=pdf_slice, mime_type="application/pdf"))
            contents.append(
                "الشريحة/الصفحة المرفقة أعلاه جزء من المادة المصدرية نفسها. "
                "اقرأها بعناية، واستخرج منها ما يخدم المادة، مع الالتزام الصارم بقواعد أمانة المصدر."
            )
        try:
            response = generate_gemini_content(
                self.client,
                models=self.models,
                operation="EDITORIAL_DRAFT",
                context={"source_name": source_name},
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiTelegramDraft,
                ),
                validator=_require_editorial_draft,
            )
        except Exception as exc:
            raise_if_provider_outcome_unknown(exc, provider="Gemini text drafting")
            raise
        parsed = response.parsed
        if parsed is None or not parsed.content.strip():
            raise ValueError("Gemini returned no editorial draft.")
        return parsed.content.strip()
