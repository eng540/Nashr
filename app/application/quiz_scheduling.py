"""Execution path for scheduled native Telegram quiz Artifacts."""
import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.adapters.publishing.telegram import TelegramPublisher
from app.application.artifacts import load_artifact
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.domain.scheduling import ScheduleItemStatus, ScheduleStatus
from app.infrastructure.database.models import ArtifactModel, PublicationModel, ScheduleItemModel, ScheduleModel
from app.infrastructure.database.session import SessionFactory


async def execute_quiz_schedule_item(item_id: UUID, publisher=None, destination: str | None = None) -> None:
    destination = destination or os.getenv("TELEGRAM_DESTINATION_ID", "")
    async with SessionFactory() as session:
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.id == item_id))).scalar_one_or_none()
        if item is None or item.artifact_id is None:
            return
        artifact_row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == item.artifact_id))).scalar_one_or_none()
        if artifact_row is None or artifact_row.kind != "QUIZ":
            item.status = ScheduleItemStatus.FAILED.value
            item.last_error = "Scheduled Artifact is missing or is not a QUIZ."
            item.processing_started_at = None
            await session.commit()
            return
        published = (await session.execute(select(PublicationModel).where(
            PublicationModel.artifact_id == artifact_row.id,
            PublicationModel.platform == "telegram",
            PublicationModel.status == "PUBLISHED",
        ).limit(1))).scalar_one_or_none()
        if published is not None:
            item.status = ScheduleItemStatus.SKIPPED.value
            item.publication_id = published.id
            item.published_at = published.published_at
            item.processing_started_at = None
            await session.commit()
            return
        if not destination:
            item.status = ScheduleItemStatus.FAILED.value
            item.last_error = "TELEGRAM_DESTINATION_ID is required."
            item.processing_started_at = None
            await session.commit()
            return
        if artifact_row.status != "AVAILABLE" or artifact_row.review_status != "APPROVED":
            item.status = ScheduleItemStatus.CANCELLED.value
            item.last_error = "QUIZ Artifact is no longer approved and available."
            item.processing_started_at = None
            await session.commit()
            return
        artifact = await load_artifact(session, artifact_row.id)
        if artifact is None:
            item.status = ScheduleItemStatus.FAILED.value
            item.last_error = "Scheduled QUIZ Artifact could not be loaded."
            item.processing_started_at = None
            await session.commit()
            return
        existing = (await session.execute(select(PublicationModel).where(
            PublicationModel.artifact_id == artifact.id,
            PublicationModel.platform == "telegram",
            PublicationModel.destination == destination,
        ).order_by(PublicationModel.created_at.asc()).limit(1))).scalar_one_or_none()
        if existing is not None and existing.status in ("READY", "PUBLISHING"):
            item.status = ScheduleItemStatus.FAILED.value
            item.last_error = "Quiz publication is already in progress; automatic retry is unsafe."
            item.publication_id = existing.id
            item.processing_started_at = None
            await session.commit()
            return
        if existing is not None and existing.status == "FAILED":
            existing.status = "DRAFT"
            existing.error_message = None
            await session.commit()
            publication_id = existing.id
        elif existing is not None:
            publication_id = existing.id
        else:
            publication_id = (await CreateTelegramDraft.execute_for_artifact(session, artifact, destination)).id

    async with SessionFactory() as session:
        try:
            publication = await ApproveAndPublish(publisher or TelegramPublisher()).execute(
                session, publication_id, artifact=artifact
            )
        except Exception as exc:
            publication = None
            error = str(exc)
        else:
            error = publication.error_message
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.id == item_id))).scalar_one_or_none()
        if item is None:
            return
        item.publication_id = publication_id if publication is None else publication.id
        item.processing_started_at = None
        if publication is not None and publication.status.value == "PUBLISHED":
            item.status = ScheduleItemStatus.PUBLISHED.value
            item.published_at = publication.published_at
            item.last_error = None
        else:
            item.status = ScheduleItemStatus.FAILED.value
            item.last_error = error or "Quiz publication failed."
        await session.commit()
        schedule = (await session.execute(select(ScheduleModel).where(ScheduleModel.id == item.schedule_id))).scalar_one_or_none()
        if schedule is not None and schedule.status == ScheduleStatus.ACTIVE.value:
            statuses = list((await session.execute(select(ScheduleItemModel.status).where(ScheduleItemModel.schedule_id == schedule.id))).scalars().all())
            if statuses and all(value in ("PUBLISHED", "SKIPPED", "FAILED", "CANCELLED") for value in statuses):
                schedule.status = ScheduleStatus.COMPLETED.value
                schedule.completed_at = datetime.now(timezone.utc)
                await session.commit()
