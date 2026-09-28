import asyncio
import logging
import os

from google import genai
from google.genai import types
from google.genai.errors import APIError, ServerError
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.domain.editorial import IEditorialDrafter

logger = logging.getLogger(__name__)


class GeminiTelegramDraft(BaseModel):
    """Define the structured Gemini response for a Telegram draft."""

    content: str


def _is_transient_error(exc: Exception) -> bool:
    """Determine if a Gemini failure is temporary and worth retrying."""
    if isinstance(exc, ServerError):
        # يغطي أخطاء 503 High Demand و 500 و 504
        return True
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status in (429, 500, 502, 503, 504):
            return True
    text = str(exc).lower()
    return any(w in text for w in ("503", "unavailable", "high demand", "resource_exhausted", "too many requests"))


class GeminiEditorialDrafter(IEditorialDrafter):
    """Draft publication-ready Telegram content with visual grounding and self-healing retries."""

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
        """Initialize the Gemini client and model configuration."""
        self._client = client
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

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
        """Run the blocking Gemini editorial request with resilient retries."""
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

        @retry(
            reraise=True,
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=1.5, min=2, max=10),
            retry=retry_if_exception_type(Exception),
            retry_error_callback=lambda state: logger.warning("event=DRAFT_RETRY attempt=%s", state.attempt_number),
        )
        def _execute_call():
            try:
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiTelegramDraft,
                    ),
                )
            except Exception as exc:
                if _is_transient_error(exc):
                    logger.warning("event=GEMINI_TRANSIENT_SPIKE error=%s - retrying...", str(exc))
                    raise exc
                # إذا كان الخطأ غير قابل للتعافي لا نعيد المحاولة
                raise

        response = _execute_call()
        parsed = response.parsed
        if parsed is None or not parsed.content.strip():
            raise ValueError("Gemini returned no editorial draft.")
        return parsed.content.strip()