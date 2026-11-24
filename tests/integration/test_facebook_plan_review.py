from uuid import UUID
import pytest
from sqlalchemy import select,func
from app.application import facebook_plan_review as flow
from app.infrastructure.database.models import PlatformCopyModel,FacebookExecutionModel,ScheduleModel,ArtifactModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_facebook_execution import seed
from tests.integration.test_instagram_oauth import config,browser
CHOICES=dict(page_id='123',public_page_acknowledged=True,rights_confirmed=True)

@pytest.mark.asyncio
async def test_private_exact_review_hash_no_jobs_history_and_cancel():
    uid,_=await seed()
    async with SessionFactory() as s:
        counts=[await s.scalar(select(func.count()).select_from(m)) for m in [FacebookExecutionModel,ScheduleModel]]
        p=await flow.preview(s,uid,**CHOICES)
        assert p['can_save_draft'] and p['blockers'] and not p['page_verified'] and not p['execution_enabled'] and not p['job_created']
        d=await flow.save_draft(s,uid,preview_hash=p['preview_hash'],**CHOICES)
        assert not d['stale'] and (await flow.save_draft(s,uid,preview_hash=p['preview_hash'],**CHOICES))['id']==d['id']
        assert counts==[await s.scalar(select(func.count()).select_from(m)) for m in [FacebookExecutionModel,ScheduleModel]]
        copy=await s.get(PlatformCopyModel,(uid,'facebook'));copy.fields={**copy.fields,'description':'تغيير'};await s.commit()
        with pytest.raises(ValueError):await flow.save_draft(s,uid,preview_hash=p['preview_hash'],**CHOICES)
        assert (await flow.list_drafts(s,uid))['items'][0]['stale']
        await flow.cancel_draft(s,uid,UUID(d['id']))
        assert (await flow.list_drafts(s,uid))['items'][0]['state']=='CANCELLED'
        with pytest.raises(ValueError):await flow.cancel_draft(s,UUID(int=0),UUID(d['id']))

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('page_id',None),('public_page_acknowledged',False),('rights_confirmed',False)])
async def test_explicit_choices_gate_saving(field,value):
    uid,_=await seed()
    async with SessionFactory() as s:
        options={**CHOICES,field:value};p=await flow.preview(s,uid,**options);assert not p['can_save_draft']
        with pytest.raises(ValueError):await flow.save_draft(s,uid,preview_hash=p['preview_hash'],**options)

@pytest.mark.asyncio
async def test_photo_preview_no_storage_network_or_execution(monkeypatch):
    import httpx
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    uid,_=await seed('IMAGE')
    def forbidden(*a,**kw):raise AssertionError('No external effects or reads')
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',forbidden);monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    async with SessionFactory() as s:
        p=await flow.preview(s,uid,**CHOICES);assert p['inspection'] is None and p['can_save_draft']
        assert 'storage_uri' not in str(p) and 'token' not in str(p)
        await flow.save_draft(s,uid,preview_hash=p['preview_hash'],**CHOICES)

@pytest.mark.asyncio
async def test_history_survives_source_kind_change():
    uid,_=await seed()
    async with SessionFactory() as s:
        p=await flow.preview(s,uid,**CHOICES);d=await flow.save_draft(s,uid,preview_hash=p['preview_hash'],**CHOICES)
        row=await s.get(ArtifactModel,uid);row.kind='VIDEO';await s.commit()
        assert (await flow.list_drafts(s,uid))['items'][0]['stale']
        await flow.cancel_draft(s,uid,UUID(d['id']))

@pytest.mark.asyncio
async def test_owner_strict_same_origin_no_execution(config):
    import httpx
    from app.main import app
    uid,_=await seed();base=f'/api/connections/facebook/materials/{uid}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.post(base+'/preview',json=CHOICES)).status_code==401
    async with browser() as c:
        assert (await c.post(base+'/preview',json={**CHOICES,'authorized':True})).status_code==422
        assert (await c.post(base+'/preview',json={**CHOICES,'rights_confirmed':'yes'})).status_code==422
        assert (await c.post(base+'/preview',json=CHOICES,headers={'Origin':'https://evil.invalid'})).status_code==403
        p=(await c.post(base+'/preview',json=CHOICES)).json()
        assert p['can_save_draft'] and (await c.post(base+'/drafts',json={**CHOICES,'preview_hash':p['preview_hash']})).status_code==200
        assert (await c.post(base+'/publish',json={})).status_code==404
