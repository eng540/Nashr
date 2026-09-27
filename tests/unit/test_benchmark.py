from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.api.benchmark import slice_pdf_pages_as_bytes


def _make_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as stream:
        writer.write(stream)


def test_slice_pdf_pages_is_bounded_and_centered(tmp_path: Path) -> None:
    source = tmp_path / "book.pdf"
    _make_pdf(source, 20)

    sliced = slice_pdf_pages_as_bytes(str(source), page_start=9, page_end=10)

    pages = PdfReader(BytesIO(sliced)).pages
    assert len(pages) == 10


def test_slice_pdf_pages_handles_short_documents(tmp_path: Path) -> None:
    source = tmp_path / "short.pdf"
    _make_pdf(source, 3)

    sliced = slice_pdf_pages_as_bytes(str(source), page_start=1, page_end=1)

    assert len(PdfReader(BytesIO(sliced)).pages) == 3
