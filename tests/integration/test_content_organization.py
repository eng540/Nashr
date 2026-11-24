from uuid import UUID,uuid4
from datetime import datetime,timezone
import pytest
from sqlalchemy import select
from tests.integration.test_managed_connections import config,browser
from tests.integration.test_platform_variants import _seed_text_artifact
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,ArtifactOrganizationModel,ScheduleModel
from app.application.distribution_readiness import source_fingerprint

@pytest.mark.asyncio
async def test_catalog_is_separate_from_source_approval_copies_and_schedule(config):
    uid=await _seed_text_artifact('أصل كامل لا يتغير بسبب عنوان الفهرسة')
    async with browser() as client:
        assert (await client.post(f'/api/artifacts/{uid}/approve',json={})).status_code==200
        before=(await client.get(f'/api/artifacts/{uid}')).json()
        copies=(await client.get(f'/api/artifacts/{uid}/platform-copies')).json()
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,UUID(uid));fingerprint=source_fingerprint(row)
        result=await client.post('/api/artifacts/organization',json={'artifact_ids':[uid],'fields':{'title':'عنوان منظم','series':'سلسلة هندسة','category':'تقنية'},'versions':{uid:0}})
        assert result.status_code==200,result.text
        assert result.json()['content_changed'] is False and result.json()['sent_messages']==0
        assert (await client.get(f'/api/artifacts/{uid}')).json()==before
        assert (await client.get(f'/api/artifacts/{uid}/platform-copies')).json()==copies
        listed=(await client.get('/api/artifacts?review_status=APPROVED&limit=100')).json()['items']
        item=next(i for i in listed if i['id']==uid);assert item['organization']['title']=='عنوان منظم' and item['organization']['version']==1
        async with SessionFactory() as session:
            assert source_fingerprint(await session.get(ArtifactModel,UUID(uid)))==fingerprint
        stale=await client.post('/api/artifacts/organization',json={'artifact_ids':[uid],'fields':{'series':'بديل'},'versions':{uid:0}});assert stale.status_code==409

@pytest.mark.asyncio
async def test_batch_atomic_missing_and_conflict_and_partial_fields(config):
    ids=[await _seed_text_artifact('تنظيم دفعة دون نشر') for _ in range(2)]
    async with browser() as client:
        data={'artifact_ids':ids,'fields':{'series':'دفعة محفوظة'},'versions':dict.fromkeys(ids,0)}
        assert (await client.post('/api/artifacts/organization',json=data)).status_code==200
        single={'artifact_ids':[ids[0]],'fields':{'category':'مخصص'},'versions':{ids[0]:1}}
        assert (await client.post('/api/artifacts/organization',json=single)).status_code==200
        # One stale version rejects every row, not half the batch.
        data['fields']={'series':'لا تحفظ'};data['versions']=dict.fromkeys(ids,1)
        assert (await client.post('/api/artifacts/organization',json=data)).status_code==409
        async with SessionFactory() as session:
            a,b=[await session.get(ArtifactOrganizationModel,UUID(uid)) for uid in ids]
            assert a.series==b.series=='دفعة محفوظة' and a.category=='مخصص' and b.category==''
        data['fields']={'title':'لا نستبدل عناوين دفعة'};assert (await client.post('/api/artifacts/organization',json=data)).status_code==409
        data['fields']={};assert (await client.post('/api/artifacts/organization',json=data)).status_code==409
        data['fields']={'series':'x'};data['artifact_ids']=[ids[0],str(uuid4())];assert (await client.post('/api/artifacts/organization',json=data)).status_code==409

@pytest.mark.asyncio
async def test_catalog_auth_csrf_validation_and_explicit_clear(config):
    uid=await _seed_text_artifact('بيانات فهرسة')
    data={'artifact_ids':[uid],'fields':{'series':'سلسلة'},'versions':{uid:0}}
    async with browser() as client:
        assert (await client.post('/api/artifacts/organization',headers={'Origin':'https://foreign.invalid'},json=data)).status_code==403
        assert (await client.post('/api/artifacts/organization',json={**data,'fields':{'series':'a'*201}})).status_code==422
        assert (await client.post('/api/artifacts/organization',json=data)).status_code==200
        assert (await client.post('/api/artifacts/organization',json={**data,'fields':{'series':''},'versions':{uid:1}})).status_code==200
    async with SessionFactory() as session:assert (await session.get(ArtifactOrganizationModel,UUID(uid))).series==''
