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
        raise GeminiOperationError(GEMINI_EMPTY_RESPONSE, "Gemini returned no editorial draft.", True)


class GeminiEditorialDrafter(IEditorialDrafter):
    """Draft publication-ready Telegram content with retry + multi-model failover."""

    SYSTEM_PROMPT = """أنت محرر محتوى تراثي وأدبي رفيع، متخصص في تحويل المادة المصدرية إلى منشورات تيليجرام رصينة، غنية ومكتملة.
مهمتك صياغة منشور متكامل الأركان يعتمد على الوثيقة المرفقة والمادة المصدرية دون أي بتر أو اختصار مخل.

قواعد التحرير الصارمة:
- ابدأ بسطر افتتاحي جذاب وذكي (Hook) دون ابتذال أو مبالغة.
- اذكر سياق الموقف كاملاً: صاحب القصة أو الرواية، والمجلس، وأطراف الحوار بدقة.
- أورد نصوص الشواهد كاملة دون تلخيص: الآيات القرآنية بنصها المضبوط وتخريجها، والأشعار والأنساب كما وردت.
- اشرح الفائدة أو الإسقاط السلوكي العملي للقارئ المعاصر.
- اختم باسم الكتاب ووسوم مناسبة وقليلة.
- استخدم Markdown المناسب لتيليجرام.
- لا تضف شرحًا خارج المنشور، وأخرج المنشور النهائي فقط داخل الحقل content.
"""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        """Initialize with a prioritized cascade of models."""
        self._client = client
        raw_models = model or os.getenv("GEMINI_MODEL", "")
        self.model = raw_models
        self.models = list(parse_model_chain(raw_models))
        logger.info("event=DRAFT_CASCADE_CONFIGURED models=%s", self.models)

    @property
    def client(self) -> genai.Client:
        """Create the Gemini client only when a real draft is requested."""
        if self._client is None:
            self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return self._client

    async def draft(
        self,
        *,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
    ) -> str:
        """Generate a complete Telegram post without blocking the event loop."""
        return await asyncio.to_thread(self._draft_sync, title, content, source_name, pdf_slice)

    def _draft_sync(
        self,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
    ) -> str:
        """Run the blocking request: retry each model, then fall back to the next."""
        prompt = (
            f"اسم الكتاب: {source_name}\n"
            f"عنوان الفكرة: {title}\n"
            f"المادة المصدرية:\n{content}\n\n"
        )
        contents: list[object] = [self.SYSTEM_PROMPT]
        if pdf_slice:
            prompt += (
                "أمامك شريحة PDF بصرية موضعية من الكتاب تغطي سياق هذه المادة بدقة. "
                "استخرج تفاصيل القصة وأطراف الحوار والشواهد بنصها الكامل كما وردت، "
                "ثم صغ منها منشور تيليجرام مكتملًا وجاهزًا للنشر دون بتر أو اختصار."
            )
            contents.extend([prompt, types.Part.from_bytes(data=pdf_slice, mime_type="application/pdf")])
        else:
            prompt += "اعتمد على المادة المصدرية المتاحة دون اختلاق أي اقتباس أو معلومة."
            contents.append(prompt)

        response = generate_gemini_content(
            self.client,
            models=self.model,
            operation="EDITORIAL_DRAFT",
            context={"source_name": source_name},
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