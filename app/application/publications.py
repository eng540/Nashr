from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.publications import IPublisher, Publication, PublicationStatus
from app.infrastructure.database.models import KnowledgeUnitModel, PublicationModel


def _to_domain(row: PublicationModel) -> Publication:
    """Convert a publication row to its domain model."""
    return Publication(id=row.id, knowledge_unit_id=row.knowledge_unit_id, platform=row.platform, destination=row.destination, content=row.content, status=PublicationStatus(row.status), external_id=row.external_id, error_message=row.error_message, created_at=row.created_at, published_at=row.published_at)


class CreateTelegramDraft:
    """Create a Telegram publication draft from one knowledge unit."""

    async def execute(self, session: AsyncSession, knowledge_unit_id: UUID, destination: str) -> Publication:
        """Create a DRAFT publication for the selected knowledge unit."""
        result = await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.id == knowledge_unit_id))
        unit = result.scalar_one_or_none()
        if unit is None:
            raise ValueError("Knowledge unit not found.")
        row = PublicationModel(id=uuid4(), knowledge_unit_id=unit.id, platform="telegram", destination=destination, content=unit.content, status=PublicationStatus.DRAFT.value)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _to_domain(row)


class ApproveAndPublish:
    """Approve a publication and publish it through a platform adapter."""

    def __init__(self, publisher: IPublisher) -> None:
        """Initialize the publisher."""
        self.publisher = publisher

    async def execute(self, session: AsyncSession, publication_id: UUID) -> Publication:
        """Publish a draft and record success or failure in the ledger."""
        claimed = await session.execute(update(PublicationModel).where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.DRAFT.value).values(status=PublicationStatus.READY.value))
        if claimed.rowcount != 1:
            raise ValueError("Publication is not a DRAFT.")
        await session.commit()

        claimed = await session.execute(update(PublicationModel).where(PublicationModel.id == publication_id, PublicationModel.status == PublicationStatus.READY.value).values(status=PublicationStatus.PUBLISHING.value, error_message=None))
        if claimed.rowcount != 1:
            raise ValueError("Publication is not READY.")
        await session.commit()

        result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
        row = result.scalar_one()
        try:
            published = await self.publisher.publish(destination=row.destination, content=row.content)
        except Exception as exc:
            await session.execute(update(PublicationModel).where(PublicationModel.id == publication_id).values(status=PublicationStatus.FAILED.value, error_message=str(exc)))
            await session.commit()
            result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
            return _to_domain(result.scalar_one())

        await session.execute(update(PublicationModel).where(PublicationModel.id == publication_id).values(status=PublicationStatus.PUBLISHED.value, external_id=published.external_id, published_at=datetime.now(timezone.utc), error_message=None))
        await session.commit()
        result = await session.execute(select(PublicationModel).where(PublicationModel.id == publication_id))
        return _to_domain(result.scalar_one())
