import io
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pypdf import PdfReader, PdfWriter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.editorial import IEditorialDrafter
from app.domain.publications import IPublisher, Publication, PublicationStatus
from app.infrastructure.database.models import KnowledgeUnitModel, PublicationModel


def slice_pdf_pages_as_bytes(
    pdf_path: str,
    page_start: int,
    page_end: int,
    window_size: int = 10,
) -> bytes:
    """Return an in-memory PDF slice centered on the material's page range."""
    if window_size < 1:
        raise ValueError("window_size must be positive")
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError("PDF contains no pages")

    center = (max(1, page_start) + max(1, page_end)) // 2
    start_idx = max(0, center - (window_size // 2) - 1)
    end_idx = min(total_pages, start_idx + window_size)
    if end_idx - start_idx < window_size:
        start_idx = max(0, end_idx - window_size)

    writer = PdfWriter()
    for index in range(start_idx, end_idx):
        writer.add_page(reader.pages[index])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _to_domain(row: PublicationModel) -> Publication:
    """Convert a publication row to its domain model."""
    return Publication(
        id=row.id,
        knowledge_unit_id=row.knowledge_unit_id,
        platform=row.platform,
        destination=row.destination,
        content=row.content,
        status=PublicationStatus(row.status),
        external_id=row.external_id,
        error_message=row.error_message,
        created_at=row.created_at,
        published_at=row.published_at,
    )


class CreateTelegramDraft:
    """Create a Telegram draft grounded by the source's visual PDF context."""

    def __init__(self, drafter: IEditorialDrafter) -> None:
        """Initialize the editorial drafter."""
        self.drafter = drafter

    async def execute(self, session: AsyncSession, knowledge_unit_id: UUID, destination: str) -> Publication:
        """Create a DRAFT publication from an editorially generated post."""
        result = await session.execute(
            select(KnowledgeUnitModel)
            .options(selectinload(KnowledgeUnitModel.source))
            .where(KnowledgeUnitModel.id == knowledge_unit_id)
        )
        unit = result.scalar_one_or_none()
        if unit is None:
            raise ValueError("Knowledge unit not found.")

        source = unit.source
        source_name = source.book_title or source.filename if source is not None else "المصدر"
        pdf_slice: bytes | None = None
        if source is not None and unit.discovery_page_start is not None and unit.discovery_page_end is not None:
            try:
                storage_path = source.ensure_file_on_disk()
                pdf_slice = slice_pdf_pages_as_bytes(
                    str(storage_path),
                    unit.discovery_page_start,
                    unit.discovery_page_end,
                    window_size=10,
                )
            except Exception:
                # Older records may have a missing or malformed PDF; preserve the text fallback.
                pdf_slice = None

        content = await self.drafter.draft(
            title=unit.title,
            content=unit.content,
            source_name=source_name,
            pdf_slice=pdf_slice,
        )
        row = PublicationModel(
            id=uuid4(),
            knowledge_unit_id=unit.id,
            platform="telegram",
            destination=destination,
            content=content,
            status=PublicationStatus.DRAFT.value,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _to_domain(row)


class ApproveAndPublish:
    """Approve a publication and publish it through a platform adapter."""

    def __init__(self, publisher: IPublisher) -> None:
        """Initialize the publisher."""
        self.publisher = publisher

    async def execute(self, session: AsyncSession, publication_id: UUID, content: str | None = None) -> Publication:
        """Persist optional user edits, then publish and record the final content."""
        if content is not None:
            content = content.strip()
            if not content:
                raise ValueError("Publication content cannot be empty.")
            edited = await session.execute(
                update(PublicationModel)
                .where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.DRAFT.value)
                .values(content=content)
            )
            if edited.rowcount != 1:
                raise ValueError("Publication is not a DRAFT.")
            await session.commit()

        claimed = await session.execute(
            update(PublicationModel)
            .where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.DRAFT.value)
            .values(status=PublicationStatus.READY.value)
        )
        if claimed.rowcount != 1:
            raise ValueError("Publication is not a DRAFT.")
        await session.commit()

        claimed = await session.execute(
            update(PublicationModel)
            .where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.READY.value)
            .values(status=PublicationStatus.PUBLISHING.value, error_message=None)
        )
        if claimed.rowcount != 1:
            raise ValueError("Publication is not READY.")
        await session.commit()

        result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
        row = result.scalar_one()
        try:
            published = await self.publisher.publish(destination=row.destination, content=row.content)
        except Exception as exc:
            await session.execute(
                update(PublicationModel)
                .where(PublicationModel.id == publication_id)
                .values(status=PublicationStatus.FAILED.value, error_message=str(exc))
            )
            await session.commit()
            result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
            return _to_domain(result.scalar_one())

        await session.execute(
            update(PublicationModel)
            .where(PublicationModel.id == publication_id)
            .values(
                status=PublicationStatus.PUBLISHED.value,
                external_id=published.external_id,
                published_at=datetime.now(timezone.utc),
                error_message=None,
            )
        )
        await session.commit()
        result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
        return _to_domain(result.scalar_one())
