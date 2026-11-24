from uuid import UUID, uuid4
from datetime import datetime, timezone
import httpx
import pytest
from sqlalchemy import select, func
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel, PostModel, PublicationModel, ScheduleModel, ScheduleItemModel
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
async def test_queue_unifies_originals_without_post_wrapper_duplicates_or_mutation():
    token='queue-'+uuid4().hex
    uid=await _seed_text_artifact(token+' original')
    excluded=await _seed_text_artifact(token+' derived')
    draft=await _seed_text_artifact(token+' draft')
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid));a.review_status='APPROVED'
        b=await s.get(ArtifactModel,UUID(excluded));b.review_status='APPROVED';b.artifact_metadata={'source_type':'PLATFORM_VARIANT'}
        post=PostModel(knowledge_unit_id=a.source_knowledge_unit_id,content=token+' editorial',status='APPROVED');s.add(post);await s.flush()
        s.add(ArtifactModel(source_knowledge_unit_id=a.source_knowledge_unit_id,kind='POST',status='AVAILABLE',post_id=post.id,review_status='APPROVED',content=token+' wrapper'))
        post_id=str(post.id);await s.commit()
        before=[(await s.execute(select(func.count()).select_from(m))).scalar_one() for m in [PublicationModel,ScheduleModel]]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        r=await c.get('/api/publishing-queue',params={'q':token});assert r.status_code==200,r.text
        data=r.json();assert data['total']==2
        assert {(x['origin'],x['id']) for x in data['items']}=={('ARTIFACT',uid),('POST',post_id)}
        assert all(x['execution_ready'] is False for x in data['items'])
        assert all(x['state']=='APPROVED' for x in data['items'])
        assert (await c.get('/api/publishing-queue',params={'q':token,'origin':'ARTIFACT'})).json()['total']==1
        assert (await c.get('/api/publishing-queue',params={'q':token,'limit':1,'offset':1})).json()['total']==2
        assert len((await c.get('/api/publishing-queue',params={'q':token,'limit':1,'offset':1})).json()['items'])==1
        for params in [{'origin':'INVALID'},{'state':'READY'},{'limit':101},{'offset':-1}]:assert (await c.get('/api/publishing-queue',params=params)).status_code==422
    async with SessionFactory() as s:
        after=[(await s.execute(select(func.count()).select_from(m))).scalar_one() for m in [PublicationModel,ScheduleModel]]
        assert before==after
        assert (await s.get(ArtifactModel,UUID(draft))).review_status=='DRAFT'


@pytest.mark.asyncio
async def test_queue_distinguishes_confirmed_publication_from_claim_and_active_plan():
    token='queue-status-'+uuid4().hex
    uid=await _seed_text_artifact(token)
    now=datetime.now(timezone.utc)
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid));a.review_status='APPROVED'
        pub=PublicationModel(knowledge_unit_id=a.source_knowledge_unit_id,artifact_id=a.id,platform='telegram',destination='test',content=token,status='PUBLISHED')
        s.add(pub);await s.commit();pub_id=pub.id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        async def state():return (await c.get('/api/publishing-queue',params={'q':token})).json()['items'][0]['state']
        assert await state()=='APPROVED'
        async with SessionFactory() as s:
            pub=await s.get(PublicationModel,pub_id);pub.external_id='confirmed';await s.commit()
        assert await state()=='PUBLISHED'
        async with SessionFactory() as s:
            plan=ScheduleModel(name=token,status='DRAFT',timezone='Asia/Riyadh');s.add(plan);await s.flush()
            s.add(ScheduleItemModel(schedule_id=plan.id,artifact_id=UUID(uid),position=1,scheduled_at=now,status='PENDING'));await s.commit();plan_id=plan.id
        assert await state()=='PLANNED'
        assert (await c.get('/api/publishing-queue',params={'q':token,'state':'PLANNED'})).json()['total']==1
        async with SessionFactory() as s:
            plan=await s.get(ScheduleModel,plan_id);plan.status='CANCELLED';await s.commit()
        assert await state()=='PUBLISHED'

@pytest.mark.asyncio
async def test_queue_reports_failed_plan_and_stale_selection_without_preparing_missing_copies():
    token='queue-prep-'+uuid4().hex
    uid=await _seed_text_artifact(token)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        assert (await c.post(f'/api/artifacts/{uid}/approve',json={})).status_code==200
        readiness=(await c.get(f'/api/artifacts/{uid}/distribution-readiness')).json()
        assert (await c.post('/api/artifacts/distribution-selection',json={'artifact_ids':[uid],'platforms':['telegram'],'fingerprints':{uid:readiness['source_fingerprint']}})).status_code==200
        async with SessionFactory() as s:
            a=await s.get(ArtifactModel,UUID(uid));a.content=token+' changed'
            plan=ScheduleModel(name=token,status='PAUSED',timezone='Asia/Riyadh');s.add(plan);await s.flush()
            s.add(ScheduleItemModel(schedule_id=plan.id,artifact_id=a.id,position=1,scheduled_at=datetime.now(timezone.utc),status='FAILED'));await s.commit()
        data=(await c.get('/api/publishing-queue',params={'q':token})).json();assert data['total']==1
        row=data['items'][0];assert row['state']=='ATTENTION';assert row['selection_stale'] is True
        assert row['selected_platforms']==['telegram'];assert row['prepared_copies']==6
        assert row['fields_validated']==0
        assert (await c.get('/api/publishing-queue',params={'q':token,'state':'PUBLISHED'})).json()['total']==0
