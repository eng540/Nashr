import os

import pytest

from app.adapters.extraction.gemini import GeminiExtractor
from app.domain.sources import Source


@pytest.mark.gemini
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY is not configured")
async def test_gemini_extractor_returns_five_ideas(tmp_path) -> None:
    """Optionally verify Gemini returns five structured ideas."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n")
    source = Source.stored("sample.pdf", "application/pdf", str(pdf_path), pdf_path.stat().st_size)
    ideas = await GeminiExtractor().extract(source)
    assert len(ideas) == 5
    assert [idea.position for idea in ideas] == [1, 2, 3, 4, 5]
