from datetime import datetime,timedelta,timezone
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,ScheduleModel,ScheduleItemModel,PublicationModel
from tests.integration.test_scheduling import _post
from tests.integration.test_media_scheduling import _media_artifact

@pytest.mark.asyncio
async def test_calendar_and_upcoming_mix_artifact_and_post_without_mutating():
    artifact_id=await _media_artifact();_,_,_,post_id=await _post('Mixed calendar post')
    schedule_id=uuid4();at=datetime.now(timezone.utc)+timedelta(hours=1)
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,artifact_id);row.artifact_metadata={**(row.artifact_metadata or {}),'title':'صورة التقويم'}
        session.add(ScheduleModel(id=schedule_id,name='Mixed read test',timezone='Asia/Riyadh',status='ACTIVE'))
        await session.flush()
        session.add_all([ScheduleItemModel(schedule_id=schedule_id,artifact_id=artifact_id,position=1,status='PENDING',scheduled_at=at),ScheduleItemModel(schedule_id=schedule_id,post_id=post_id,position=2,status='PENDING',scheduled_at=at)])
        await session.commit()
    local=at+timedelta(hours=3)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for url in [f'/schedules/calendar?date={local.date()}&timezone=Asia/Riyadh','/schedules/upcoming?days=2']:
            response=await client.get(url);assert response.status_code==200,response.text
            rows=[r for r in response.json()['items'] if r['schedule_id']==str(schedule_id)]
            assert len(rows)==2
            image=next(r for r in rows if r['artifact_id']==str(artifact_id))
            assert image['post_id'] is None and image['title']=='صورة التقويم' and image['id']==image['item_id']
            post=next(r for r in rows if r['post_id']==str(post_id));assert post['artifact_id'] is None and post['title']=='Mixed calendar post'
    async with SessionFactory() as session:
        items=(await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id==schedule_id))).scalars().all()
        assert all(i.status=='PENDING' and i.attempts==0 for i in items)
        assert not (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id==artifact_id))).scalars().all()
