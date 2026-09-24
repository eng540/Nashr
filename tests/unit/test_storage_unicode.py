from pathlib import Path

import pytest

from app.infrastructure.storage import LocalFileStorage


@pytest.mark.asyncio
async def test_local_storage_uses_ascii_safe_path_for_arabic_filename(tmp_path: Path) -> None:
    storage = LocalFileStorage(str(tmp_path))

    stored_path = await storage.save("مرآة المروءات.pdf", b"%PDF-test", prefix="source-123")

    assert Path(stored_path).name == "source-123_source.pdf"
    assert stored_path.isascii()
    assert Path(stored_path).read_bytes() == b"%PDF-test"
