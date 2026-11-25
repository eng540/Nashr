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

@pytest.mark.asyncio
async def test_calendar_pages_beyond_old_limit_without_duplicates_or_writes():
    artifact_id=await _media_artifact();schedule_id=uuid4();at=datetime(2032,1,1,22,30,tzinfo=timezone.utc)
    async with SessionFactory() as s:
        artifact_ids=[]
        template=await s.get(ArtifactModel,artifact_id)
        for _ in range(205):
            row=ArtifactModel(kind='IMAGE',status='AVAILABLE',source_knowledge_unit_id=template.source_knowledge_unit_id,artifact_metadata={'title':'synthetic'},review_status='APPROVED');s.add(row);await s.flush();artifact_ids.append(row.id)
        s.add(ScheduleModel(id=schedule_id,name='Many calendar rows',timezone='Asia/Riyadh',status='ACTIVE'));await s.flush()
        s.add_all([ScheduleItemModel(schedule_id=schedule_id,artifact_id=artifact_ids[i],position=i,status='CANCELLED' if i==204 else 'PENDING',scheduled_at=at+timedelta(seconds=i)) for i in range(205)])
        await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        ids=[]
        for offset in range(0,205,20):
            r=await c.get('/schedules/calendar',params={'date':'2032-01-02','timezone':'Asia/Riyadh','limit':20,'offset':offset});assert r.status_code==200,r.text
            j=r.json();assert j['total']==205 and j['offset']==offset and j['limit']==20
            ids.extend(i['id'] for i in j['items']);assert all(i['schedule_id']==str(schedule_id) for i in j['items'])
        assert len(ids)==len(set(ids))==205
        assert (await c.get('/schedules/calendar?date=2032-01-01&timezone=Asia/Riyadh')).json()['total']==0
        assert (await c.get('/schedules/calendar?date=2032-01-02&offset=-1')).status_code==422
        assert (await c.get('/schedules/upcoming?offset=-1')).status_code==422
    async with SessionFactory() as s:
        rows=(await s.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id==schedule_id))).scalars().all();assert len(rows)==205 and all(r.attempts==0 for r in rows)

@pytest.mark.asyncio
async def test_upcoming_total_is_not_page_size_and_only_active_pending():
    artifact_id=await _media_artifact();sid=uuid4();at=datetime.now(timezone.utc)+timedelta(hours=2)
    async with SessionFactory() as s:
        artifact_ids=[]
        template=await s.get(ArtifactModel,artifact_id)
        for _ in range(26):
            row=ArtifactModel(kind='IMAGE',status='AVAILABLE',source_knowledge_unit_id=template.source_knowledge_unit_id,artifact_metadata={'title':'synthetic'},review_status='APPROVED');s.add(row);await s.flush();artifact_ids.append(row.id)
        s.add(ScheduleModel(id=sid,name='Upcoming pages',timezone='UTC',status='ACTIVE'));await s.flush()
        s.add_all([ScheduleItemModel(schedule_id=sid,artifact_id=artifact_ids[i],position=i,status='PENDING' if i<25 else 'CANCELLED',scheduled_at=at+timedelta(seconds=i)) for i in range(26)]);await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        a=(await c.get('/schedules/upcoming?limit=20&offset=0')).json();b=(await c.get('/schedules/upcoming?limit=20&offset=20')).json()
        assert a['total']==b['total'] and a['total']>=25 and b['offset']==20
        assert len(a['items'])==20 and len(b['items'])>=5
        assert not(set(x['id'] for x in a['items'])&set(x['id'] for x in b['items']))
