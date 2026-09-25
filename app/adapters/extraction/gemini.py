import asyncio
import os
from pathlib import Path

from google import genai
from pydantic import BaseModel, Field

from app.domain.extraction import ExtractedIdea, IExtractor
from app.domain.sources import Source


class GeminiIdea(BaseModel):
    """Define one Gemini structured-output idea."""
    position: int
    title: str
    content: str


class GeminiIdeas(BaseModel):
    """Define the exact five-idea Gemini response."""
    ideas: list[GeminiIdea] = Field(min_length=5, max_length=5)


class GeminiExtractor(IExtractor):
    """Extract exactly five ideas from a PDF using Gemini structured output."""

    SYSTEM_PROMPT = """أنت مستخرج أفكار من الكتب، ولست ملخّصاً للفهرس أو الوصف الببليوغرافي.

استخرج بالضبط خمس أفكار جوهرية ومتمايزة من متن الكتاب، مع الحفاظ على معنى المصدر.
تجاهل صراحةً ولا تعتبر مصدراً للأفكار: صفحات الفهارس، قوائم المراجع والمصادر، ومقدمات التحقيق والتقديمات التحريرية الخاصة بالمحقق أو الناشر.
ركّز على الدرر الفكرية، والحجج والمعاني الجوهرية، والمواقف العملية المباشرة التي يمكن تحويلها إلى معرفة نافعة للقارئ.
تجنّب الملخصات الوصفية العامة من نوع "يتحدث الكتاب عن..."، ولا تستخرج عناوين الفصول أو موضوعات الفهرس بدلاً من الفكرة نفسها.
لا تخترع معلومات أو اقتباسات غير مدعومة بالمصدر.
Return positions 1 through 5."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        """Initialize the Gemini client and model configuration."""
        self.client = client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        """Extract exactly five ideas from the stored PDF."""
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._extract_sync, source)

    def _extract_sync(self, source: Source) -> list[ExtractedIdea]:
        """Run the blocking Gemini request in a worker thread."""
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
            raise ValueError("Gemini returned no structured extraction.")
        ideas = [
            ExtractedIdea(position=item.position, title=item.title, content=item.content)
            for item in parsed.ideas
        ]
        if [idea.position for idea in ideas] != [1, 2, 3, 4, 5]:
            raise ValueError("Gemini returned invalid idea positions.")
        return ideas
