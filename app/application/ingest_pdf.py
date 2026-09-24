from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.sources import Source, SourceStatus
from app.infrastructure.database.models import SourceModel
from app.infrastructure.storage import LocalFileStorage


class IngestPdf:
    """Store a PDF and register its source metadata."""

    def __init__(self, storage: LocalFileStorage) -> None:
        """Initialize PDF ingestion with file storage."""
        self.storage = storage

    async def execute(self, session: AsyncSession, filename: str, mime_type: str, content: bytes) -> Source:
        """Validate, store, and persist a PDF source."""
        if mime_type != "application/pdf" and not filename.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are supported.")
        source_id = uuid4()
        storage_path = await self.storage.save(filename, content, prefix=str(source_id))
        row = SourceModel(
            id=source_id,
            filename=filename,
            mime_type=mime_type or "application/pdf",
            storage_path=storage_path,
            size_bytes=len(content),
            status=SourceStatus.STORED.value,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.to_domain()
