import asyncio
import logging
import os
import time

from google import genai
from google.genai import types
from google.genai.errors import APIError, ServerError
from pydantic import BaseModel

from app.domain.editorial import IEditorialDrafter

logger = logging.getLogger(__name__)

DEFAULT_MODEL_CASCADE = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
]

ATTEMPTS_PER_MODEL = 2
BASE_DELAY_SECONDS = 2.0


class GeminiTelegramDraft(BaseModel):
    """Define the structured Gemini response for a Telegram draft."""

    content: str


def _is_transient_error(exc: Exception) -> bool:
    """Check whether a Gemini failure is transient and eligible for retry/failover."""
    if isinstance(exc, ServerError):
        return True
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status in (429, 500, 502, 503, 504):
            return True
    text = str(exc).lower()
    return any(
        w in text
        for w in ("503", "unavailable", "high demand", "resource_exhausted", "too many requests", "rate limit")
    )


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
        if raw_models.strip():
            self.models = [m.strip() for m in raw_models.split(",") if m.strip()]
        else:
            self.models = DEFAULT_MODEL_CASCADE
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

        last_error: Exception | None = None

        for candidate_model in self.models:
            for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
                try:
                    logger.info(
                        "event=DRAFT_ATTEMPT model=%s attempt=%s/%s",
                        candidate_model, attempt, ATTEMPTS_PER_MODEL,
                    )
                    response = self.client.models.generate_content(
                        model=candidate_model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=GeminiTelegramDraft,
                        ),
                    )
                    parsed = response.parsed
                    if parsed and parsed.content.strip():
                        logger.info("event=DRAFT_SUCCESS model=%s attempt=%s", candidate_model, attempt)
                        return parsed.content.strip()
                    logger.warning("event=DRAFT_EMPTY_RESPONSE model=%s attempt=%s", candidate_model, attempt)
                    last_error = ValueError(f"Model {candidate_model} returned an empty draft.")
                except Exception as exc:
                    if not _is_transient_error(exc):
                        logger.error("event=DRAFT_PERMANENT_ERROR model=%s error=%s", candidate_model, str(exc))
                        raise
                    last_error = exc
                    logger.warning(
                        "event=DRAFT_TRANSIENT_ERROR model=%s attempt=%s/%s error=%s",
                        candidate_model, attempt, ATTEMPTS_PER_MODEL, str(exc),
                    )
                    # إن كانت هناك محاولة أخرى لنفس النموذج، انتظر ثم أعد
                    if attempt < ATTEMPTS_PER_MODEL:
                        delay = BASE_DELAY_SECONDS * attempt
                        logger.info("event=DRAFT_BACKOFF seconds=%s", delay)
                        time.sleep(delay)
                        continue
                    # استُنفدت محاولات هذا النموذج: انتقل للتالي
                    logger.warning(
                        "event=MODEL_FAILOVER exhausted=%s -> trying next model in cascade...",
                        candidate_model,
                    )
                    break

        if last_error is not None:
            raise last_error
        raise RuntimeError("Model cascade is empty; no Gemini model was configured.")