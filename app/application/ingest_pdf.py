from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.sources import Source
from app.infrastructure.database.models import SourceModel
from app.infrastructure.storage import LocalFileStorage

class IngestPdf:
    """Validate, store, and register an uploaded PDF source."""

    def __init__(self, storage: LocalFileStorage) -> None:
        """Initialize the PDF ingestion use case."""
        self.storage = storage

    async def execute(self, session: AsyncSession, filename: str, mime_type: str, content: bytes) -> Source:
        """Store a PDF and persist its source record as STORED."""
        if mime_type != "application/pdf" or not content.startswith(b"%PDF-"):
            raise ValueError("Only valid PDF uploads are supported.")
        safe_name = Path(filename).name
        storage_path = await self.storage.save(safe_name, content)
        source = Source.stored(safe_name, mime_type, storage_path, len(content))
        session.add(SourceModel(id=source.id, filename=source.filename, mime_type=source.mime_type, storage_path=source.storage_path, size_bytes=source.size_bytes, status=source.status.value, created_at=source.created_at))
        await session.commit()
        return source
