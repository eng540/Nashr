from pathlib import Path

import pytest

from app.infrastructure.storage import LocalFileStorage


@pytest.mark.asyncio
async def test_save_uses_ascii_safe_storage_name_for_unicode_filename(tmp_path: Path) -> None:
    """Store a Unicode-named file under an ASCII-safe unique path."""
    storage = LocalFileStorage(str(tmp_path))

    path = Path(await storage.save("مرآة المروءات.pdf", b"pdf", prefix="source-123"))

    assert path.read_bytes() == b"pdf"
    assert path.suffix == ".pdf"
    assert path.name == "source-123.pdf"
    assert path.name.isascii()


@pytest.mark.asyncio
async def test_save_without_prefix_generates_ascii_safe_unique_name(tmp_path: Path) -> None:
    """Generate a unique ASCII-safe filename when no source prefix is supplied."""
    storage = LocalFileStorage(str(tmp_path))

    path = Path(await storage.save("مرآة المروءات.pdf", b"pdf"))

    assert path.read_bytes() == b"pdf"
    assert path.suffix == ".pdf"
    assert path.name.isascii()
