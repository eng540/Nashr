import logging
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

import app.application.editorial_context as editorial_context
from app.adapters.extraction.gemini import GeminiBookMapper


@pytest.fixture
def pdf_with_noisy_reader(monkeypatch):
    """Emit pypdf's known warning from a reader wrapper around a real PDF."""
    real_reader = editorial_context.PdfReader

    def noisy_reader(path):
        logging.getLogger("pypdf._reader").warning("Object 17 0 not defined.")
        logging.getLogger("pypdf._reader").warning("A different pypdf warning.")
        return real_reader(path)

    monkeypatch.setattr(editorial_context, "PdfReader", noisy_reader)


def _make_pdf(path: Path, page_count: int) -> None:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as stream:
        writer.write(stream)


def test_slice_suppresses_only_known_warning_and_preserves_page_count(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pdf_with_noisy_reader
) -> None:
    source = tmp_path / "book.pdf"
    _make_pdf(source, 20)
    pdf_logger = logging.getLogger("pypdf._reader")
    previous_level = pdf_logger.level

    with caplog.at_level(logging.WARNING, logger="pypdf._reader"):
        sliced = editorial_context.slice_pdf_pages_as_bytes(
            str(source), page_start=9, page_end=10, window_size=10
        )

    assert len(PdfReader(BytesIO(sliced)).pages) == 10
    assert "Object 17 0 not defined." not in caplog.text
    assert "A different pypdf warning." in caplog.text
    assert pdf_logger.level == previous_level


def test_slice_does_not_suppress_known_warning_outside_its_scope(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pdf_with_noisy_reader
) -> None:
    source = tmp_path / "book.pdf"
    _make_pdf(source, 2)
    pdf_logger = logging.getLogger("pypdf._reader")

    with caplog.at_level(logging.WARNING, logger="pypdf._reader"):
        editorial_context.slice_pdf_pages_as_bytes(str(source), 1, 1, window_size=2)
        pdf_logger.warning("Object 21 0 not defined.")

    assert "Object 17 0 not defined." not in caplog.text
    assert "Object 21 0 not defined." in caplog.text


def test_invalid_pdf_raises_instead_of_becoming_a_successful_slice(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"this is not a PDF")

    with pytest.raises(PdfReadError):
        editorial_context.slice_pdf_pages_as_bytes(str(invalid), 1, 1)


def test_gemini_book_mapper_keeps_scoped_warning_behavior(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pdf_logger = logging.getLogger("pypdf._reader")
    previous_level = pdf_logger.level

    with caplog.at_level(logging.WARNING, logger="pypdf._reader"):
        with GeminiBookMapper._quiet_pypdf_warnings():
            pdf_logger.warning("Object 9 0 not defined.")
            pdf_logger.warning("A different pypdf warning.")
        pdf_logger.warning("Object 10 0 not defined.")

    assert "Object 9 0 not defined." not in caplog.text
    assert "A different pypdf warning." in caplog.text
    assert "Object 10 0 not defined." in caplog.text
    assert pdf_logger.level == previous_level


def test_suppression_does_not_hide_warning_from_another_thread(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    pdf_logger = logging.getLogger("pypdf._reader")

    with caplog.at_level(logging.WARNING, logger="pypdf._reader"):
        with editorial_context.quiet_known_pypdf_warnings():
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(
                    pdf_logger.warning, "Object 31 0 not defined."
                ).result()

    assert "Object 31 0 not defined." in caplog.text
