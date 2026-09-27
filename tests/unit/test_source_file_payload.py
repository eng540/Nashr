from pathlib import Path
from uuid import uuid4

import pytest

from app.infrastructure.database.models import SourceModel


def _source(path: Path, payload: bytes | None) -> SourceModel:
    return SourceModel(
        id=uuid4(),
        filename="book.pdf",
        mime_type="application/pdf",
        storage_path=str(path),
        size_bytes=len(payload or b""),
        status="STORED",
        file_payload=payload,
    )


def test_ensure_file_on_disk_restores_database_payload(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "book.pdf"
    payload = b"%PDF-persisted"

    restored = _source(path, payload).ensure_file_on_disk()

    assert restored == path
    assert path.read_bytes() == payload


def test_ensure_file_on_disk_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "book.pdf"
    path.write_bytes(b"%PDF-local")
    source = _source(path, b"%PDF-database")

    source.ensure_file_on_disk()

    assert path.read_bytes() == b"%PDF-local"


def test_ensure_file_on_disk_raises_without_payload(tmp_path: Path) -> None:
    source = _source(tmp_path / "missing.pdf", None)

    with pytest.raises(FileNotFoundError):
        source.ensure_file_on_disk()
