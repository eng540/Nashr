from pathlib import Path

import pytest

from app.adapters.extraction.gemini import GeminiBookMapper
from app.domain.sources import Source


class FakeFile:
    def __init__(self, name="files/test", uri="https://example.test/file", mime_type="application/pdf", state=None):
        self.name = name
        self.uri = uri
        self.mime_type = mime_type
        self.state = state


class FakeFiles:
    def __init__(self, existing=None):
        self.existing = existing
        self.upload_calls = 0
        self.get_calls = 0

    def upload(self, file):
        self.upload_calls += 1
        return FakeFile()

    def get(self, name):
        self.get_calls += 1
        if self.existing is None:
            raise RuntimeError("not found")
        return self.existing


class FakeClient:
    def __init__(self, existing=None):
        self.files = FakeFiles(existing)


@pytest.mark.asyncio
async def test_gemini_document_reference_is_reused_without_upload(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-test")
    source = Source.stored("book.pdf", "application/pdf", str(pdf), pdf.stat().st_size)
    source = Source(
        **{
            **source.__dict__,
            "content_sha256": "same-hash",
            "gemini_file_name": "files/existing",
            "gemini_file_source_sha256": "same-hash",
        }
    )

    client = FakeClient(FakeFile(name="files/existing"))
    mapper = GeminiBookMapper(client=client)

    document = await mapper.prepare_document(source)

    assert document.name == "files/existing"
    assert client.files.get_calls == 1
    assert client.files.upload_calls == 0
