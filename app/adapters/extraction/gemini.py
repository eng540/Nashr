import asyncio
import os
from pathlib import Path

from google import genai
from pydantic import BaseModel, Field

from app.domain.extraction import ExtractedIdea, IExtractor
from app.domain.sources import Source


class GeminiIdea(BaseModel):
    """Define one structured material discovered by Gemini."""
    position: int = Field(ge=1)
    title: str
    content: str
    original_text: str | None = None
    source_reference: str | None = None


class GeminiIdeas(BaseModel):
    """Define the structured Gemini discovery response."""
    ideas: list[GeminiIdea]


class GeminiExtractor(IExtractor):
    """Discover zero or more materials from a PDF using Gemini structured output."""

    SYSTEM_PROMPT = """أنت مستكشف مواد تحريرية من الكتب، ولست ملخّصاً للفهرس أو الوصف الببليوغرافي.

اكتشف من متن الكتاب المواد التي يمكن أن تصبح أساساً لمحتوى تحريري جيد. أعد صفر مادة أو أكثر؛ لا تحاول ملء عدد محدد من العناصر.
يمكن أن تكون المادة فكرة، اقتباساً، قصة، موقفاً، معنى، سؤالاً، جواباً، معلومة، وصفاً، شخصية، حدثاً، شعراً، مقطعاً أدبياً، مقارنة، مفارقة، درساً، أو أي مادة أخرى ذات قيمة تحريرية.
لا تستخدم قائمة مغلقة لأنواع المحتوى ولا تصنّف المادة إلا إذا كان ذلك مفيداً لوصفها.
تجاهل صفحات الفهارس وقوائم المراجع والمصادر ومقدمات التحقيق والتقديمات التحريرية الخاصة بالمحقق أو الناشر عندما لا تكون هي المادة الأصلية المقصودة.
حافظ على معنى المصدر ولا تخترع معلومات أو اقتباسات غير مدعومة بالمصدر.
إذا أمكن تحديد الصفحة أو الموضع من الوثيقة، أعده في source_reference. أعد original_text عندما تكون المادة مقتبسة أو عندما يفيد حفظ النص الأصلي في تتبعها.
رقّم المواد بترتيب ظهورها أو أهميتها ابتداءً من 1. لا تستخدم الرقم لفرض عدد معين من المواد."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        """Initialize the Gemini client and model configuration."""
        self.client = client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Discover zero or more materials from the stored PDF."""
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._extract_sync, source)

    def _extract_sync(self, source: Source) -> list[ExtractedIdea]:
        """Upload the original PDF to Gemini File API and run structured discovery."""
        if not Path(source.storage_path).is_file():
            raise FileNotFoundError(source.storage_path)
        uploaded_file = self.client.files.upload(file=source.storage_path)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[self.SYSTEM_PROMPT, uploaded_file],
            config={
                "response_mime_type": "application/json",
                "response_schema": GeminiIdeas,
            },
        )
        parsed = response.parsed
        if parsed is None:
            raise ValueError("Gemini returned no structured discovery.")
        ideas = [
            ExtractedIdea(
                position=item.position,
                title=item.title,
                content=item.content,
                original_text=item.original_text,
                source_reference=item.source_reference,
            )
            for item in parsed.ideas
        ]
        positions = [idea.position for idea in ideas]
        if positions != list(range(1, len(ideas) + 1)):
            raise ValueError("Gemini returned invalid material positions.")
        return ideas
