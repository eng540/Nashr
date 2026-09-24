from pathlib import Path

import pytest

from app.infrastructure.storage import LocalFileStorage


@pytest.mark.asyncio
async def test_save_uses_ascii_safe_path_for_unicode_pdf_filename(tmp_path: Path) -> None:
    """Store a Unicode PDF filename using an ASCII-safe physical path."""
    storage = LocalFileStorage(str(tmp_path))

    path = Path(await storage.save("مرآة المروءات.pdf", b"pdf", prefix="source-123"))

    assert path.read_bytes() == b"pdf"
    assert path.suffix == ".pdf"
    assert path.name == "source-123_source.pdf"
    assert path.name.isascii()
