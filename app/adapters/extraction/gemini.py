import asyncio
import hashlib
import io
import json
import logging
import os
import re
import time
from pathlib import Path
from contextlib import contextmanager

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter

from app.adapters.gemini_policy import (
    GeminiOperationError,
    classify_gemini_error,
    create_gemini_client,
    generate_content as generate_gemini_content,
)
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
أنت تعمل على نافذة محدودة من الكتاب؛ افهم فقط ما تثبته الصفحات الممررة لك، ولا تدّعِ معرفة ما خارجها.
استخرج البنية الموضوعية الظاهرة في هذه النافذة: الأقسام والمحاور والموضوعات ذات المعنى التي تكشف تنظيم المحتوى فعلاً.
لا تفترض أن كل كتاب له فصول رسمية. قد يكون التجميع موضوعياً أو مفاهيمياً أو زمنياً أو أدبياً أو غير ذلك.
لا تستخدم تصنيفاً مغلقاً ولا تفرض عدداً معيناً من الموضوعات. إذا لم توجد موضوعات ذات معنى فأعد topics فارغة.
لا تستخرج مواد منشورات في هذه الخطوة ولا تخترع عناوين.
لكل موضوع، أعد page_start و page_end كأرقام الصفحات المطلقة في الكتاب، على أن تقع بالكامل داخل النافذة الممررة.
source_reference اختياري ولا يوضع إلا إذا كان مدعوماً من الصفحات الممررة.
حافظ على ترتيب ظهور الأقسام عندما يكون واضحاً."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        self.client = client or create_gemini_client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL")

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
        """Build a global book map without ever sending the whole PDF in one request."""
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._map_sync, source, document)

    async def map_book_hierarchical(self, source: Source, document: DocumentReference) -> BookMap:
        """Compatibility-facing name for the bounded, hierarchical mapper."""
        return await self.map_book(source, document)

    def _map_sync(self, source: Source, document: DocumentReference) -> BookMap:
        path = Path(source.storage_path)
        if not path.is_file():
            raise FileNotFoundError(source.storage_path)

        with self._quiet_pypdf_warnings():
            reader = PdfReader(str(path))
        page_count = len(reader.pages)
        if page_count == 0:
            raise GeminiOperationError("GEMINI_INVALID_ARGUMENT", "PDF contains no pages.")

        max_pages = max(1, int(os.getenv("GEMINI_BOOK_MAP_MAX_PAGES_PER_SECTION", "64")))
        sections = self._page_ranges(page_count, max_pages)
        logger.info(
            "event=BOOK_MAP_SECTIONS_PLANNED source_id=%s page_count=%s section_count=%s max_pages=%s",
            source.id, page_count, len(sections), max_pages,
        )

        local_maps: list[GeminiBookMap] = []
        for index, (page_start, page_end) in enumerate(sections, start=1):
            logger.info(
                "event=BOOK_MAP_SECTION_START source_id=%s section=%s/%s pages=%s-%s",
                source.id, index, len(sections), page_start, page_end,
            )
            local_maps.extend(
                self._map_section_adaptive(
                    source,
                    reader,
                    page_start,
                    page_end,
                    section_index=index,
                )
            )

        return self._merge_local_maps(source, local_maps, page_count, len(sections))

    @staticmethod
    def _page_ranges(page_count: int, max_pages: int) -> list[tuple[int, int]]:
        return [
            (start, min(start + max_pages - 1, page_count))
            for start in range(1, page_count + 1, max_pages)
        ]

    def _map_section_adaptive(
        self,
        source: Source,
        reader: PdfReader,
        page_start: int,
        page_end: int,
        *,
        section_index: int,
    ) -> list[GeminiBookMap]:
        try:
            return [self._map_section(source, reader, page_start, page_end, section_index)]
        except GeminiOperationError as exc:
            cause_text = str(getattr(exc, "cause", None) or exc).lower()
            context_limit = (
                "maximum number of tokens" in cause_text
                or "token count exceeds" in cause_text
                or "context window" in cause_text
            )
            if not context_limit or page_start >= page_end:
                raise
            midpoint = (page_start + page_end) // 2
            logger.warning(
                "event=BOOK_MAP_SECTION_SPLIT source_id=%s section=%s pages=%s-%s midpoint=%s",
                source.id, section_index, page_start, page_end, midpoint,
            )
            left = self._map_section_adaptive(source, reader, page_start, midpoint, section_index=section_index)
            right = self._map_section_adaptive(source, reader, midpoint + 1, page_end, section_index=section_index)
            return left + right

    def _map_section(
        self,
        source: Source,
        reader: PdfReader,
        page_start: int,
        page_end: int,
        section_index: int,
    ) -> GeminiBookMap:
        bounded_pdf = self._bounded_pdf(reader, page_start, page_end)
        prompt = (
            "هذه نافذة محدودة من كتاب وليست الكتاب كاملاً. "
            f"حلّل فقط صفحات PDF {page_start}-{page_end}. "
            "استخرج البنية الموضوعية الظاهرة في هذه النافذة، ويمكن للموضوع أن يبدأ أو ينتهي خارجها؛ "
            "في هذه الحالة اجعل page_start/page_end حدوداً محافظة لما تثبته هذه النافذة فقط. "
            "لا تنشئ مواد منشورات. "
            "أعد page_start و page_end كأرقام الصفحات المطلقة في الكتاب، وليس أرقاماً نسبية داخل النافذة."
        )
        try:
            response = generate_gemini_content(
                self.client,
                models=self.model,
                operation="BUILDING_BOOK_MAP_SECTION",
                context={
                    "source_id": source.id,
                    "section_index": section_index,
                    "page_start": page_start,
                    "page_end": page_end,
                },
                contents=[
                    self.SYSTEM_PROMPT,
                    prompt,
                    types.Part.from_bytes(data=bounded_pdf, mime_type="application/pdf"),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiBookMap,
                ),
            )
        except Exception as exc:
            code, retryable = classify_gemini_error(exc)
            raise GeminiOperationError(code, "Gemini bounded book-map generation failed.", retryable, exc) from exc

        self._log_usage(response, source.id, "BUILDING_BOOK_MAP_SECTION")
        parsed = response.parsed
        if parsed is None:
            raise GeminiOperationError("GEMINI_INVALID_RESPONSE", "Gemini returned no section book map.")

        topics: list[GeminiTopic] = []
        for item in parsed.topics:
            if item.page_start > item.page_end:
                raise GeminiOperationError("GEMINI_SCHEMA_ERROR", "Gemini returned an inverted section topic range.")
            if item.page_start < page_start or item.page_end > page_end:
                raise GeminiOperationError(
                    "GEMINI_PROVENANCE_UNAVAILABLE",
                    f"Section topic pages {item.page_start}-{item.page_end} escape bounded window {page_start}-{page_end}.",
                )
            topics.append(item)

        return GeminiBookMap(
            title=parsed.title.strip(),
            description=parsed.description.strip(),
            topics=topics,
        )

    def _merge_local_maps(
        self,
        source: Source,
        local_maps: list[GeminiBookMap],
        page_count: int,
        section_count: int,
    ) -> BookMap:
        if not local_maps:
            return BookMap(
                source_id=source.id,
                title=source.filename,
                description="",
                topics=[],
            )
        if len(local_maps) == 1:
            parsed = local_maps[0]
        else:
            parsed = self._merge_maps_hierarchical(
                source,
                local_maps,
                page_count,
                section_count,
            )

        positions = [topic.position for topic in parsed.topics]
        if positions != list(range(1, len(positions) + 1)):
            raise GeminiOperationError("GEMINI_SCHEMA_ERROR", "Gemini returned invalid merged topic positions.")

        topics: list[BookTopic] = []
        for item in parsed.topics:
            if item.page_start > item.page_end or item.page_start < 1 or item.page_end > page_count:
                raise GeminiOperationError(
                    "GEMINI_PROVENANCE_UNAVAILABLE",
                    f"Gemini returned topic pages outside the source: {item.page_start}-{item.page_end}.",
                )
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

        return BookMap(
            source_id=source.id,
            title=parsed.title.strip() or source.filename,
            description=parsed.description.strip(),
            topics=topics,
        )

    def _merge_maps_hierarchical(
        self,
        source: Source,
        maps: list[GeminiBookMap],
        page_count: int,
        section_count: int,
    ) -> GeminiBookMap:
        current = maps
        round_index = 1
        while len(current) > 1:
            next_level: list[GeminiBookMap] = []
            batch_size = max(2, int(os.getenv("GEMINI_BOOK_MAP_MERGE_BATCH_SIZE", "6")))
            for batch_index in range(0, len(current), batch_size):
                batch = current[batch_index:batch_index + batch_size]
                next_level.append(
                    self._merge_maps_batch(
                        source,
                        batch,
                        page_count,
                        section_count,
                        round_index,
                        batch_index // batch_size + 1,
                    )
                )
            current = next_level
            round_index += 1
        return current[0]

    def _merge_maps_batch(
        self,
        source: Source,
        maps: list[GeminiBookMap],
        page_count: int,
        section_count: int,
        round_index: int,
        batch_index: int,
    ) -> GeminiBookMap:
        payload = json.dumps(
            [
                {
                    "section": index,
                    "title": item.title,
                    "description": item.description,
                    "topics": [topic.model_dump() for topic in item.topics],
                }
                for index, item in enumerate(maps, start=1)
            ],
            ensure_ascii=False,
        )
        prompt = f"""أنت الآن تقوم بدمج خرائط محلية متجاورة لكتاب واحد.
ادمج فقط البنية المدعومة في الخرائط الممررة، بما في ذلك دمج الموضوعات المتصلة عبر حدود النوافذ عندما تدعمها الأدلة.
رتّب الموضوعات حسب ظهورها في الكتاب.
لا تخترع موضوعاً جديداً غير موجود في الخرائط.
لا تستخدم تصنيفاً مغلقاً ولا تفرض عدداً معيناً.
حافظ على page_start/page_end كحدود PDF مطلقة.
أعد عنوان الكتاب ووصفه من الأدلة المتاحة.
يجب أن تكون جميع page_start/page_end بين 1 و {page_count}.
هذه مرحلة دمج، وليست مرحلة استخراج مواد منشورات.

جولة الدمج: {round_index}
دفعة الدمج: {batch_index}
عدد النوافذ الأصلية في المهمة: {section_count}

الخرائط:
{payload}
"""
        try:
            response = generate_gemini_content(
                self.client,
                models=self.model,
                operation="BUILDING_BOOK_MAP_MERGE",
                context={
                    "source_id": source.id,
                    "section_count": section_count,
                    "merge_round": round_index,
                    "merge_batch": batch_index,
                    "map_count": len(maps),
                },
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiBookMap,
                ),
            )
        except Exception as exc:
            code, retryable = classify_gemini_error(exc)
            raise GeminiOperationError(code, "Gemini book-map merge failed.", retryable, exc) from exc

        self._log_usage(response, source.id, "BUILDING_BOOK_MAP_MERGE")
        parsed = response.parsed
        if parsed is None:
            raise GeminiOperationError("GEMINI_INVALID_RESPONSE", "Gemini returned no merged book map.")
        return parsed

    @staticmethod
    @contextmanager
    def _quiet_pypdf_warnings():
        pdf_logger = logging.getLogger("pypdf._reader")
        previous_level = pdf_logger.level
        pdf_logger.setLevel(logging.ERROR)
        try:
            yield
        finally:
            pdf_logger.setLevel(previous_level)

    @staticmethod
    def _bounded_pdf(reader: PdfReader, page_start: int, page_end: int) -> bytes:
        if page_start < 1 or page_end < page_start:
            raise GeminiOperationError("GEMINI_INVALID_ARGUMENT", "Invalid PDF page range.")
        if page_end > len(reader.pages):
            raise GeminiOperationError(
                "GEMINI_INVALID_ARGUMENT",
                f"Requested page range {page_start}-{page_end} exceeds PDF page count {len(reader.pages)}.",
            )
        writer = PdfWriter()
        with GeminiBookMapper._quiet_pypdf_warnings():
            for page_index in range(page_start - 1, page_end):
                writer.add_page(reader.pages[page_index])
            output = io.BytesIO()
            writer.write(output)
        return output.getvalue()

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
        logger.info("event=GEMINI_USAGE source_id=%s stage=%s usage=%s", source.id, stage, fields)


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
        self.client = client or create_gemini_client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL")

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
            "event=GEMINI_BOUNDED_INPUT source_id=%s topic_id=%s chunk=%s pages=%s-%s bytes=%s",
            source.id, topic.id, span.chunk_index, span.page_start, span.page_end, len(bounded_pdf),
        )
        try:
            response = generate_gemini_content(
                self.client,
                models=self.model,
                operation="DISCOVERING_MATERIALS",
                context={"source_id": source.id, "topic_id": topic.id, "chunk_index": span.chunk_index},
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
        with GeminiBookMapper._quiet_pypdf_warnings():
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
        self.client = client or create_gemini_client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or os.getenv("GEMINI_MODEL")

    async def extract(self, source: Source) -> list[ExtractedIdea]:
        if source.mime_type != "application/pdf":
            raise ValueError("Gemini extraction requires a PDF source.")
        return await asyncio.to_thread(self._extract_sync, source)

    def _extract_sync(self, source: Source) -> list[ExtractedIdea]:
        if not Path(source.storage_path).is_file():
            raise FileNotFoundError(source.storage_path)
        uploaded_file = self.client.files.upload(file=source.storage_path)
        response = generate_gemini_content(
            self.client,
            models=self.model,
            operation="FLAT_EXTRACTION",
            context={"source_id": source.id},
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
