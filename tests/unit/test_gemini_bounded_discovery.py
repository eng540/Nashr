from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from app.adapters.extraction.gemini import (
    GeminiOperationError,
    GeminiTopicMaterialDiscoverer,
    classify_gemini_error,
)
from app.domain.book_map import BookTopic
from app.domain.extraction import DiscoverySpan, DocumentReference
from app.domain.sources import Source


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        class Response:
            parsed = type("Ideas", (), {"ideas": []})()
            usage_metadata = None
        return Response()


class FakeClient:
    def __init__(self):
        self.models = FakeModels()
        self.files = type("Files", (), {"upload": lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("upload must not be called"))})()


def _pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    writer.write(path)


def test_bounded_pdf_contains_only_requested_pages(tmp_path: Path) -> None:
    source_path = tmp_path / "book.pdf"
    _pdf(source_path, 10)
    data = GeminiTopicMaterialDiscoverer._bounded_pdf(str(source_path), 3, 5)
    assert len(PdfReader(BytesIO(data)).pages) == 3


@pytest.mark.asyncio
async def test_topic_discovery_uses_bounded_inline_pdf_without_file_upload(tmp_path: Path) -> None:
    source_path = tmp_path / "book.pdf"
    _pdf(source_path, 6)
    source = Source.stored("book.pdf", "application/pdf", str(source_path), source_path.stat().st_size)
    topic = BookTopic.create(source.id, 1, "Topic", "Description", "pages 2-4", 2, 4)
    client = FakeClient()
    discoverer = GeminiTopicMaterialDiscoverer(client=client)
    ideas = await discoverer.discover_topic(
        source,
        topic,
        DocumentReference("unused", "fake://unused", "application/pdf"),
        DiscoverySpan(2, 4, 1),
    )
    assert ideas == []
    assert len(client.models.calls) == 1
    contents = client.models.calls[0]["contents"]
    inline = contents[-1].inline_data
    assert inline is not None
    assert inline.mime_type == "application/pdf"
    assert len(PdfReader(BytesIO(inline.data)).pages) == 3


def test_quota_is_non_retryable() -> None:
    code, retryable = classify_gemini_error(RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"))
    assert code == "GEMINI_QUOTA_EXCEEDED"
    assert retryable is False


class FakeUnparsedResponse:
    parsed = None
    usage_metadata = None

    def __init__(self, text: str):
        self.text = text


class FakeUnparsedModels(FakeModels):
    def __init__(self, response_text: str):
        super().__init__()
        self.response_text = response_text

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeUnparsedResponse(self.response_text)


class FakeUnparsedClient(FakeClient):
    def __init__(self, response_text: str):
        self.models = FakeUnparsedModels(response_text)


@pytest.mark.asyncio
async def test_topic_discovery_falls_back_to_valid_structured_json_when_parsed_is_none(tmp_path: Path) -> None:
    source_path = tmp_path / "book.pdf"
    _pdf(source_path, 2)
    source = Source.stored("book.pdf", "application/pdf", str(source_path), source_path.stat().st_size)
    topic = BookTopic.create(source.id, 1, "Topic", "Description", "pages 1-2", 1, 2)
    client = FakeUnparsedClient('{"ideas": []}')
    discoverer = GeminiTopicMaterialDiscoverer(client=client)

    ideas = await discoverer.discover_topic(
        source,
        topic,
        DocumentReference("unused", "fake://unused", "application/pdf"),
        DiscoverySpan(1, 2, 1),
    )

    assert ideas == []


@pytest.mark.asyncio
async def test_topic_discovery_rejects_empty_response_when_parsed_is_none(tmp_path: Path) -> None:
    source_path = tmp_path / "book.pdf"
    _pdf(source_path, 2)
    source = Source.stored("book.pdf", "application/pdf", str(source_path), source_path.stat().st_size)
    topic = BookTopic.create(source.id, 1, "Topic", "Description", "pages 1-2", 1, 2)
    client = FakeUnparsedClient("")
    discoverer = GeminiTopicMaterialDiscoverer(client=client)

    with pytest.raises(GeminiOperationError, match="empty material-discovery response"):
        await discoverer.discover_topic(
            source,
            topic,
            DocumentReference("unused", "fake://unused", "application/pdf"),
            DiscoverySpan(1, 2, 1),
        )
