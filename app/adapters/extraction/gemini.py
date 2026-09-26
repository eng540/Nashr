import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import DocumentReference, ExtractedIdea, IBookMapper, IExtractor, ITopicMaterialDiscoverer
from app.domain.sources import Source

logger = logging.getLogger(__name__)


class GeminiTopic(BaseModel):
    position: int = Field(ge=1)
    title: str
    description: str
    source_reference: str | None = None


class GeminiBookMap(BaseModel):
    title: str
    description: str
    topics: list[GeminiTopic]


class GeminiIdea(BaseModel):
    position: int = Field(ge=1)
    title: str
    content: str
    original_text: str | None = None
    source_reference: str | None = None
    kind: str | None = None


class GeminiIdeas(BaseModel):
    ideas: list[GeminiIdea]


class GeminiBookMapper(IBookMapper):
    """Understand a book using one reusable Gemini Files representation."""

    SYSTEM_PROMPT = """أنت مستكشف بنية كتاب، ولست كاتب محتوى.
افهم الوثيقة الأصلية كاملة، ثم أنشئ خريطة عملية تساعد المحرر على التنقل داخل الكتاب.
أعد عنوان الكتاب ووصفاً موجزاً، ثم الموضوعات/الأقسام/المحاور ذات المعنى التي تكشف تنظيم المحتوى فعلاً.
لا تفترض أن كل كتاب له فصول رسمية. قد يكون التجميع موضوعياً أو مفاهيمياً أو زمنياً أو أدبياً أو غير ذلك.
لا تستخدم تصنيفاً مغلقاً ولا تفرض عدداً معيناً من الموضوعات. إذا لم توجد موضوعات ذات معنى فأعد topics فارغة.
لا تستخرج مواد منشورات في هذه الخطوة ولا تخترع عناوين أو صفحات.
حافظ على ترتيب ظهور الأقسام عندما يكون واضحاً، وأعد source_reference فقط عندما يكون مدعوماً من الوثيقة."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        self.client = client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    async def prepare_document(self, source: Source) -> DocumentReference:
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._prepare_sync, source)

    def _source_hash(self, source: Source) -> str:
        if source.content_sha256:
            return source.content_sha256
        path = Path(source.storage_path)
        if not path.is_file():
            raise FileNotFoundError(source.storage_path)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _prepare_sync(self, source: Source) -> DocumentReference:
        path = Path(source.storage_path)
        if not path.is_file():
            raise FileNotFoundError(source.storage_path)
        source_hash = self._source_hash(source)

        if source.gemini_file_name and source.gemini_file_source_sha256 == source_hash:
            try:
                existing = self.client.files.get(name=source.gemini_file_name)
                state = getattr(getattr(existing, "state", None), "name", None)
                if state in (None, "ACTIVE"):
                    if not existing.uri or not existing.mime_type:
                        raise ValueError("Stored Gemini file has no usable URI.")
                    logger.info("gemini_document_reused source_id=%s file=%s", source.id, source.gemini_file_name)
                    return DocumentReference(existing.name, existing.uri, existing.mime_type)
                if state == "PROCESSING":
                    return self._wait_for_active(existing.name, source.id)
                logger.warning("gemini_document_unusable source_id=%s state=%s", source.id, state)
            except Exception:
                logger.exception("gemini_document_reuse_failed source_id=%s file=%s", source.id, source.gemini_file_name)

        uploaded = self.client.files.upload(file=source.storage_path)
        if not uploaded.name or not uploaded.uri or not uploaded.mime_type:
            raise ValueError("Gemini file upload returned an incomplete document reference.")
        logger.info("gemini_document_uploaded source_id=%s file=%s", source.id, uploaded.name)
        return self._wait_for_active(uploaded.name, source.id)

    def _wait_for_active(self, file_name: str, source_id) -> DocumentReference:
        deadline = time.monotonic() + float(os.getenv("GEMINI_FILE_READY_TIMEOUT_SECONDS", "180"))
        current = self.client.files.get(name=file_name)
        while True:
            state = getattr(getattr(current, "state", None), "name", None)
            if state in (None, "ACTIVE"):
                if not current.uri or not current.mime_type:
                    raise ValueError("Gemini file has no usable URI.")
                return DocumentReference(current.name, current.uri, current.mime_type)
            if state == "FAILED":
                raise RuntimeError("Gemini document processing failed.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for Gemini document processing.")
            logger.info("gemini_document_processing source_id=%s file=%s state=%s", source_id, file_name, state)
            time.sleep(2.5)
            current = self.client.files.get(name=file_name)

    async def map_book(self, source: Source, document: DocumentReference) -> BookMap:
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._map_sync, source, document)

    def _map_sync(self, source: Source, document: DocumentReference) -> BookMap:
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                self.SYSTEM_PROMPT,
                types.Part.from_uri(file_uri=document.uri, mime_type=document.mime_type),
            ],
            config={"response_mime_type": "application/json", "response_schema": GeminiBookMap},
        )
        parsed = response.parsed
        if parsed is None:
            raise ValueError("Gemini returned no book map.")
        positions = [topic.position for topic in parsed.topics]
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError("Gemini returned invalid topic positions.")
        topics = [BookTopic.create(source.id, t.position, t.title.strip(), t.description.strip(), t.source_reference) for t in parsed.topics]
        return BookMap(source_id=source.id, title=parsed.title.strip() or source.filename, description=parsed.description.strip(), topics=topics)


class GeminiTopicMaterialDiscoverer(ITopicMaterialDiscoverer):
    """Discover grounded materials one topic at a time using the same document."""

    SYSTEM_PROMPT = """أنت مستكشف مواد تحريرية داخل موضوع محدد من كتاب.
استخرج فقط المواد الموجودة فعلاً في المصدر والمرتبطة بهذا الموضوع.
لا تخترع مادة ولا تعيد صياغة فكرة عامة لمجرد أنها مناسبة لوسائل التواصل.
يمكن أن تكون المادة حكمة أو قصة أو قولاً أو لطيفة أو مفهوماً أو تعريفاً أو شعراً أو موقفاً أو مثالاً أو مفارقة أو قاعدة أو وصفاً أو سيرة أو حدثاً أو مقارنة أو أي نوع آخر حقيقي في المصدر.
هذه أمثلة وليست قائمة مغلقة؛ اكتب kind بحرية وباختصار عندما يكون مفيداً.
لا تفرض عدداً ثابتاً من المواد. أعد صفر مادة عندما لا توجد مادة مستقلة مفيدة.
لا تكرر نفس المقطع أو نفس الفكرة داخل الموضوع.
يفضل مواد مستقلة المعنى وقابلة للفهرسة على ملخصات سطحية.
حافظ على معنى المصدر والنص الأصلي عند الاقتباس.
أعد source_reference فقط إذا كان مدعوماً من الوثيقة. لا تخمن أرقام الصفحات.
رقّم النتائج من 1 داخل هذا الموضوع."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        self.client = client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    async def discover_topic(self, source: Source, topic: BookTopic, document: DocumentReference) -> list[ExtractedIdea]:
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._discover_sync, source, topic, document)

    def _discover_sync(self, source: Source, topic: BookTopic, document: DocumentReference) -> list[ExtractedIdea]:
        context = f"عنوان الكتاب: {source.filename}\\nالموضوع: {topic.title}\\nوصف الموضوع: {topic.description}"
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                self.SYSTEM_PROMPT,
                context,
                types.Part.from_uri(file_uri=document.uri, mime_type=document.mime_type),
            ],
            config={"response_mime_type": "application/json", "response_schema": GeminiIdeas},
        )
        parsed = response.parsed
        if parsed is None:
            raise ValueError("Gemini returned no topic materials.")
        positions = [item.position for item in parsed.ideas]
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError("Gemini returned invalid material positions.")
        return [
            ExtractedIdea(item.position, item.title.strip(), item.content.strip(), item.original_text, item.source_reference, item.kind.strip() if item.kind else None)
            for item in parsed.ideas
        ]


class GeminiExtractor(IExtractor):
    """Backward-compatible flat discovery adapter."""

    SYSTEM_PROMPT = """أنت مستكشف مواد تحريرية من الكتب، ولست ملخّصاً للفهرس أو الوصف الببليوغرافي. تجاهل الفهارس وقوائم المراجع ومقدمات التحقيق والتقديمات التحريرية عندما لا تكون هي المادة الأصلية المقصودة.
اكتشف من متن الكتاب المواد التي يمكن أن تصبح أساساً لمحتوى تحريري جيد. أعد صفر مادة أو أكثر؛ لا تحاول ملء عدد محدد من العناصر.
يمكن أن تكون المادة فكرة، اقتباساً، قصة، موقفاً، معنى، سؤالاً، جواباً، معلومة، وصفاً، شخصية، حدثاً، شعراً، مقطعاً أدبياً، مقارنة، مفارقة، درساً، أو أي مادة أخرى ذات قيمة تحريرية. ركّز على الدرر الفكرية والمعاني الجوهرية والمواقف العملية المباشرة.
لا تستخدم قائمة مغلقة لأنواع المحتوى. حافظ على معنى المصدر ولا تخترع معلومات أو اقتباسات.
إذا أمكن تحديد الصفحة أو الموضع من الوثيقة، أعده في source_reference. لا تخمن أرقام الصفحات.
رقّم المواد بترتيب ظهورها أو أهميتها ابتداءً من 1، ولا تستخدم الرقم لفرض عدد معين."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        self.client = client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._extract_sync, source)

    def _extract_sync(self, source: Source) -> list[ExtractedIdea]:
        if not Path(source.storage_path).is_file():
            raise FileNotFoundError(source.storage_path)
        uploaded_file = self.client.files.upload(file=source.storage_path)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[self.SYSTEM_PROMPT, uploaded_file],
            config={"response_mime_type": "application/json", "response_schema": GeminiIdeas},
        )
        parsed = response.parsed
        if parsed is None:
            raise ValueError("Gemini returned no structured discovery.")
        ideas = [ExtractedIdea(i.position, i.title, i.content, i.original_text, i.source_reference, i.kind) for i in parsed.ideas]
        if [idea.position for idea in ideas] != list(range(1, len(ideas) + 1)):
            raise ValueError("Gemini returned invalid material positions.")
        return ideas
