import asyncio
import os

from google import genai
from pydantic import BaseModel

from app.domain.editorial import IEditorialDrafter


class GeminiTelegramDraft(BaseModel):
    """Define the structured Gemini response for a Telegram draft."""
    content: str


class GeminiEditorialDrafter(IEditorialDrafter):
    """Draft publication-ready Telegram content with Gemini."""

    SYSTEM_PROMPT = """أنت محرر محتوى عربي متخصص في تحويل الفكرة الجوهرية من كتاب إلى منشور تيليجرام عالي الجودة.

مهمتك ليست تلخيص الكتاب ولا إعادة وصف الفكرة وصفاً عاماً، بل صياغة منشور مكتمل وقابل للنشر يحافظ على معنى المصدر.

قواعد التحرير:
- ابدأ بسطر افتتاحي جذاب (Hook) يلفت الانتباه دون مبالغة أو clickbait.
- فكك الفكرة بوضوح، واظهر نص الشاهد/الاقتباس كما هو عندما يكون متاحاً في المادة، مع عدم اختلاق أي اقتباس.
- اشرح الفائدة أو الإسقاط العملي المباشر للقارئ.
- اختم باسم الكتاب ثم وسوم Hashtags مناسبة وقليلة.
- استخدم Markdown مناسباً لتيليجرام.
- لا تضف مقدمات تحقيق أو معلومات عن الفهرس أو المراجع أو وصفاً خارجياً للمحتوى لمجرد ملء المنشور.
- لا تنسب للمؤلف أو الكتاب ما لا تدعمه الفكرة المصدرية.
- أخرج المنشور النهائي فقط داخل الحقل content، دون شرح لعملية الصياغة.
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

    async def draft(self, *, title: str, content: str, source_name: str) -> str:
        """Generate a complete Telegram post without blocking the event loop."""
        return await asyncio.to_thread(self._draft_sync, title, content, source_name)

    def _draft_sync(self, title: str, content: str, source_name: str) -> str:
        """Run the blocking Gemini editorial request."""
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                self.SYSTEM_PROMPT,
                f"اسم الكتاب: {source_name}\nعنوان الفكرة: {title}\nالمادة المصدرية:\n{content}",
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": GeminiTelegramDraft,
            },
        )
        parsed = response.parsed
        if parsed is None or not parsed.content.strip():
            raise ValueError("Gemini returned no editorial draft.")
        return parsed.content.strip()
