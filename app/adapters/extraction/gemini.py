import asyncio
import hashlib
import io
import logging
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter

from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import (
    DiscoverySpan,
    DocumentReference,
    ExtractedIdea,
    IBookMapper,
    IExtractor,
    ITopicMaterialDiscoverer,
)
from app.domain.sources import Source

logger = logging.getLogger(__name__)


class GeminiOperationError(RuntimeError):
    """Normalized Gemini failure carrying a stable application error code."""

    def __init__(self, code: str, message: str, retryable: bool = False, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.cause = cause


def classify_gemini_error(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, GeminiOperationError):
        return exc.code, exc.retryable
    if isinstance(exc, TimeoutError):
        return "GEMINI_FILE_TIMEOUT", True
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if "resource_exhausted" in text or "quota" in text:
        return "GEMINI_QUOTA_EXCEEDED", False
    if status == 429 or "rate limit" in text or "too many requests" in text:
        return "GEMINI_RATE_LIMITED", True
    if status in (401, 403) or "unauthenticated" in text or "permission denied" in text:
        return "GEMINI_AUTH_ERROR", False
    if status == 404 or "not found" in text:
        return "GEMINI_FILE_NOT_FOUND", False
    if status == 400 or "invalid argument" in text:
        return "GEMINI_INVALID_ARGUMENT", False
    if status and int(status) >= 500:
        return "GEMINI_SERVER_ERROR", True
    if isinstance(exc, (ConnectionError, OSError)) or "timeout" in text or "connection" in text:
        return "GEMINI_NETWORK_ERROR", True
    return "GEMINI_API_ERROR", False


class GeminiTopic(BaseModel):
    position: int = Field(ge=1)
    title: str
    description: str
    source_reference: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


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
    """Understand the book once, then provide evidence-backed topic page bounds."""

    SYSTEM_PROMPT = """أنت مستكشف بنية كتاب، ولست كاتب محتوى.
افهم الوثيقة الأصلية كاملة، ثم أنشئ خريطة عملية تساعد المحرر على التنقل داخل الكتاب.
أعد عنوان الكتاب ووصفاً موجزاً، ثم الموضوعات/الأقسام/المحاور ذات المعنى التي تكشف تنظيم المحتوى فعلاً.
لا تفترض أن كل كتاب له فصول رسمية. قد يكون التجميع موضوعياً أو مفاهيمياً أو زمنياً أو أدبياً أو غير ذلك.
لا تستخدم تصنيفاً مغلقاً ولا تفرض عدداً معيناً من الموضوعات. إذا لم توجد موضوعات ذات معنى فأعد topics فارغة.
لا تستخرج مواد منشورات في هذه الخطوة ولا تخترع عناوين.
لكل موضوع، أعد page_start و page_end كأرقام صفحات PDF التي تحتوي فعلاً على نطاق الموضوع. يجب أن تكون الحدود مدعومة بما تراه في الوثيقة؛ لا تخمن أرقام الصفحات.
إذا كان الموضوع يمتد على نطاق كبير، أعط النطاق الكامل. إذا لم يمكن تحديد نطاق مدعوم، لا تُنشئ الموضوع.
source_reference اختياري ولا يوضع إلا إذا كان مدعوماً من الوثيقة.
حافظ على ترتيب ظهور الأقسام عندما يكون واضحاً."""

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
            except Exception as exc:
                code, retryable = classify_gemini_error(exc)
                if code != "GEMINI_FILE_NOT_FOUND":
                    raise GeminiOperationError(code, "Gemini document lookup failed.", retryable, exc) from exc
            else:
                state = getattr(getattr(existing, "state", None), "name", None)
                if state in (None, "ACTIVE"):
                    if not existing.uri or not existing.mime_type:
                        raise GeminiOperationError("GEMINI_FILE_FAILED", "Stored Gemini file has no usable URI.")
                    logger.info("event=DOCUMENT_REUSED source_id=%s file=%s", source.id, source.gemini_file_name)
                    return DocumentReference(existing.name, existing.uri, existing.mime_type)
                if state == "PROCESSING":
                    return self._wait_for_active(existing.name, source.id)
                logger.warning("event=DOCUMENT_UNUSABLE source_id=%s state=%s", source.id, state)

        try:
            logger.info("event=DOCUMENT_UPLOADED source_id=%s", source.id)
            uploaded = self.client.files.upload(file=source.storage_path)
        except Exception as exc:
            code, retryable = classify_gemini_error(exc)
            raise GeminiOperationError(code, "Gemini document upload failed.", retryable, exc) from exc

        if not uploaded.name or not uploaded.uri or not uploaded.mime_type:
            raise GeminiOperationError("GEMINI_FILE_FAILED", "Gemini file upload returned an incomplete reference.")
        return self._wait_for_active(uploaded.name, source.id)

    def _wait_for_active(self, file_name: str, source_id) -> DocumentReference:
        deadline = time.monotonic() + float(os.getenv("GEMINI_FILE_READY_TIMEOUT_SECONDS", "180"))
        try:
            current = self.client.files.get(name=file_name)
        except Exception as exc:
            code, retryable = classify_gemini_error(exc)
            raise GeminiOperationError(code, "Gemini file state lookup failed.", retryable, exc) from exc
        while True:
            state = getattr(getattr(current, "state", None), "name", None)
            if state in (None, "ACTIVE"):
                if not current.uri or not current.mime_type:
                    raise GeminiOperationError("GEMINI_FILE_FAILED", "Gemini file has no usable URI.")
                logger.info("event=DOCUMENT_READY source_id=%s file=%s", source_id, file_name)
                return DocumentReference(current.name, current.uri, current.mime_type)
            if state == "FAILED":
                raise GeminiOperationError("GEMINI_FILE_FAILED", "Gemini document processing failed.")
            if time.monotonic() >= deadline:
                raise GeminiOperationError("GEMINI_FILE_TIMEOUT", "Timed out waiting for Gemini document processing.", True)
            logger.info("event=DOCUMENT_PROCESSING source_id=%s file=%s state=%s", source_id, file_name, state)
            time.sleep(2.5)
            try:
                current = self.client.files.get(name=file_name)
            except Exception as exc:
                code, retryable = classify_gemini_error(exc)
                raise GeminiOperationError(code, "Gemini file state lookup failed.", retryable, exc) from exc

    async def map_book(self, source: Source, document: DocumentReference) -> BookMap:
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._map_sync, source, document)

    def _map_sync(self, source: Source, document: DocumentReference) -> BookMap:
        logger.info("event=GEMINI_CALL stage=BUILDING_BOOK_MAP source_id=%s model=%s input=document_file", source.id, self.model)
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    self.SYSTEM_PROMPT,
                    types.Part.from_uri(file_uri=document.uri, mime_type=document.mime_type),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiBookMap,
                ),
            )
        except Exception as exc:
            code, retryable = classify_gemini_error(exc)
            raise GeminiOperationError(code, "Gemini book-map generation failed.", retryable, exc) from exc
        self._log_usage(response, source.id, "BUILDING_BOOK_MAP")
        parsed = response.parsed
        if parsed is None:
            raise GeminiOperationError("GEMINI_INVALID_RESPONSE", "Gemini returned no book map.")
        positions = [topic.position for topic in parsed.topics]
        if positions != list(range(1, len(positions) + 1)):
            raise GeminiOperationError("GEMINI_SCHEMA_ERROR", "Gemini returned invalid topic positions.")
        topics: list[BookTopic] = []
        for item in parsed.topics:
            if item.page_start > item.page_end:
                raise GeminiOperationError("GEMINI_SCHEMA_ERROR", "Gemini returned an inverted topic page range.")
            topics.append(
                BookTopic.create(
                    source.id,
                    item.position,
                    item.title.strip(),
                    item.description.strip(),
                    item.source_reference,
                    item.page_start,
                    item.page_end,
                )
            )
        return BookMap(source_id=source.id, title=parsed.title.strip() or source.filename, description=parsed.description.strip(), topics=topics)

    @staticmethod
    def _log_usage(response, source_id, stage: str) -> None:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            logger.info("event=GEMINI_USAGE_UNAVAILABLE source_id=%s stage=%s", source_id, stage)
            return
        fields = {}
        for name in ("prompt_token_count", "candidates_token_count", "total_token_count", "cached_content_token_count"):
            value = getattr(usage, name, None)
            if value is not None:
                fields[name] = value
        logger.info("event=GEMINI_USAGE source_id=%s stage=%s usage=%s", source_id, stage, fields)


class GeminiTopicMaterialDiscoverer(ITopicMaterialDiscoverer):
    """Discover materials only from a bounded PDF page span."""

    SYSTEM_PROMPT = """أنت مستكشف مواد تحريرية داخل نطاق صفحات محدد من موضوع في كتاب.
استخرج فقط المواد الموجودة فعلاً في الصفحات التي تم تمريرها لك والمرتبطة بالموضوع.
لا تخترع مادة ولا تعيد صياغة فكرة عامة لمجرد أنها مناسبة لوسائل التواصل.
يمكن أن تكون المادة حكمة أو قصة أو قولاً أو لطيفة أو مفهوماً أو تعريفاً أو شعراً أو موقفاً أو مثالاً أو مفارقة أو قاعدة أو وصفاً أو سيرة أو حدثاً أو مقارنة أو أي نوع آخر حقيقي في المصدر.
لا تفرض عدداً ثابتاً من المواد. أعد صفر مادة عندما لا توجد مادة مستقلة مفيدة في هذا النطاق.
لا تكرر نفس المقطع أو نفس الفكرة داخل النطاق.
حافظ على معنى المصدر والنص الأصلي عند الاقتباس.
أعد source_reference فقط إذا كان مدعوماً من الصفحات الممررة. لا تخمن أرقام الصفحات.
رقّم النتائج من 1 داخل هذا النطاق."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        self.client = client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    async def discover_topic(
        self,
        source: Source,
        topic: BookTopic,
        document: DocumentReference,
        span: DiscoverySpan,
    ) -> list[ExtractedIdea]:
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._discover_sync, source, topic, document, span)

    def _discover_sync(
        self,
        source: Source,
        topic: BookTopic,
        document: DocumentReference,
        span: DiscoverySpan,
    ) -> list[ExtractedIdea]:
        if span.page_start < 1 or span.page_end < span.page_start:
            raise ValueError("Invalid discovery page span.")
        bounded_pdf = self._bounded_pdf(source.storage_path, span.page_start, span.page_end)
        context = (
            f"عنوان الكتاب: {source.filename}\n"
            f"الموضوع: {topic.title}\n"
            f"وصف الموضوع: {topic.description}\n"
            f"نطاق المصدر الممرر: صفحات PDF {span.page_start}-{span.page_end}. "
            "تعامل مع هذا النطاق فقط ولا تفترض محتوى خارج الصفحات الممررة."
        )
        logger.info(
            "event=GEMINI_CALL stage=DISCOVERING_MATERIALS source_id=%s topic_id=%s chunk=%s pages=%s-%s bytes=%s model=%s input=bounded_pdf",
            source.id, topic.id, span.chunk_index, span.page_start, span.page_end, len(bounded_pdf), self.model,
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    self.SYSTEM_PROMPT,
                    context,
                    types.Part.from_bytes(data=bounded_pdf, mime_type="application/pdf"),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiIdeas,
                ),
            )
        except Exception as exc:
            code, retryable = classify_gemini_error(exc)
            raise GeminiOperationError(code, "Gemini bounded material discovery failed.", retryable, exc) from exc
        GeminiBookMapper._log_usage(response, source.id, "DISCOVERING_MATERIALS")
        parsed = response.parsed
        if parsed is None:
            raise GeminiOperationError("GEMINI_INVALID_RESPONSE", "Gemini returned no topic materials.")
        positions = [item.position for item in parsed.ideas]
        if positions != list(range(1, len(positions) + 1)):
            raise GeminiOperationError("GEMINI_SCHEMA_ERROR", "Gemini returned invalid material positions.")
        return [
            ExtractedIdea(
                item.position,
                item.title.strip(),
                item.content.strip(),
                item.original_text,
                item.source_reference,
                item.kind.strip() if item.kind else None,
            )
            for item in parsed.ideas
        ]

    @staticmethod
    def _bounded_pdf(path: str, page_start: int, page_end: int) -> bytes:
        pdf_path = Path(path)
        if not pdf_path.is_file():
            raise FileNotFoundError(path)
        reader = PdfReader(str(pdf_path))
        if page_end > len(reader.pages):
            raise GeminiOperationError(
                "GEMINI_INVALID_ARGUMENT",
                f"Requested page range {page_start}-{page_end} exceeds PDF page count {len(reader.pages)}.",
            )
        writer = PdfWriter()
        for page_index in range(page_start - 1, page_end):
            writer.add_page(reader.pages[page_index])
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()


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
