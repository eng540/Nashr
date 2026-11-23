"""Read-only artifact publication ledger. Never creates or sends a draft."""
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.generic_artifact_review import GenericArtifactReviewService
from app.infrastructure.database.models import PublicationModel, ScheduleItemModel, ScheduleModel


async def artifact_publications(session: AsyncSession, artifact_id: UUID, limit: int = 50, offset: int = 0):
    await GenericArtifactReviewService(session).get(artifact_id)
    filt = PublicationModel.artifact_id == artifact_id
    total = (await session.execute(select(func.count()).select_from(PublicationModel).where(filt))).scalar_one()
    rows = (await session.execute(select(PublicationModel).where(filt).order_by(PublicationModel.created_at.desc(), PublicationModel.id.desc()).limit(limit).offset(offset))).scalars().all()
    ids = [row.id for row in rows]
    schedules = (await session.execute(select(ScheduleItemModel, ScheduleModel.name, ScheduleModel.status).join(ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id).where(ScheduleItemModel.publication_id.in_(ids)))).all() if ids else []
    by_pub = {}
    for item, name, status in schedules:
        by_pub.setdefault(item.publication_id, []).append({"schedule_id":str(item.schedule_id),"name":name,"schedule_status":status,"item_status":item.status,"scheduled_at":item.scheduled_at,"attempts":item.attempts,"last_error":item.last_error})
    return {"items":[{"id":str(row.id),"platform":row.platform,"destination":row.destination,"status":row.status,"content":row.content,"external_id":row.external_id,"external_ids":row.external_ids or ([row.external_id] if row.external_id else []),"error_message":row.error_message,"created_at":row.created_at,"published_at":row.published_at,"schedules":by_pub.get(row.id,[])} for row in rows],"total":total,"limit":limit,"offset":offset}
