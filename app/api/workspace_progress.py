"""Read-only workspace progress. Counts describe saved state, never publishing readiness."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import ArtifactModel, PostModel, ScheduleItemModel, SourceModel

router=APIRouter(prefix='/api/workspace',tags=['workspace'])

@router.get('/progress')
async def progress(session:AsyncSession=Depends(get_session)):
    original=func.coalesce(ArtifactModel.artifact_metadata['source_type'].astext,'')!='PLATFORM_VARIANT'
    rows=(await session.execute(select(ArtifactModel.review_status,func.count()).where(ArtifactModel.kind!='POST',ArtifactModel.status=='AVAILABLE',original).group_by(ArtifactModel.review_status))).all()
    materials={str(status or 'UNREVIEWED'):int(count) for status,count in rows}
    posts={status:int(count) for status,count in (await session.execute(select(PostModel.status,func.count()).group_by(PostModel.status))).all()}
    copies=int(await session.scalar(select(func.count()).select_from(ArtifactModel).where(ArtifactModel.artifact_metadata['source_type'].astext=='PLATFORM_VARIANT')) or 0)
    failed=int(await session.scalar(select(func.count()).select_from(ScheduleItemModel).where(ScheduleItemModel.status=='FAILED')) or 0)
    pending=int(await session.scalar(select(func.count()).select_from(ScheduleItemModel).where(ScheduleItemModel.status.in_(['PENDING','PROCESSING']))) or 0)
    pdf=int(await session.scalar(select(func.count()).select_from(SourceModel).where(SourceModel.mime_type=='application/pdf')) or 0)
    return {'materials':materials,'editorial_posts':posts,'platform_copies':copies,'pdf_sources':pdf,'schedule_items':{'failed':failed,'pending_or_processing':pending},'caveat':'Saved state only. Approval is not destination readiness or publication; pending includes draft and paused plans.'}
