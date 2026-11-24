from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select,func
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramExecutionModel as Job,InstagramDirectConnectionModel as Connection,PlatformCopyModel
from app.application import instagram_direct_oauth as oauth,instagram_plan_review as review,instagram_direct_execution as direct,instagram_execution as core
from tests.integration.test_instagram_execution_core import seed,private_storage,Provider,DIGEST
from tests.integration.test_instagram_oauth import config,browser
from tests.integration.test_instagram_direct_oauth import clear,start

async def connected(monkeypatch):
    await clear()
    async def exchange(code,c):return 'private-token',dict(account_id='100',username='creator',app_scoped_id='456'),sorted(oauth.SCOPES),oauth.now()+timedelta(days=3)
    async def facts(c,e):return e['account']
    monkeypatch.setattr(oauth,'exchange',exchange);monkeypatch.setattr(oauth,'selected_facts',facts)
    async with browser() as c:
        state=await start(c);await c.get(oauth.BASE+'/callback',params={'state':state,'code':'synthetic'})
        assert (await c.post(oauth.BASE+'/select',json={'account_id':'100'})).status_code==200

async def setup(monkeypatch):
    await connected(monkeypatch);uid,_=await seed()
    async with SessionFactory() as s:
        p=await review.preview(s,uid,login_mode='INSTAGRAM_LOGIN');assert p['blockers']==[]
        d=await review.save_draft(s,uid,preview_hash=p['preview_hash'],login_mode='INSTAGRAM_LOGIN')
    return uid,UUID(d['id'])

@pytest.mark.asyncio
async def test_direct_review_and_ledger_private_idempotent_no_provider(config,monkeypatch):
    uid,rid=await setup(monkeypatch)
    def forbidden(*a,**kw):raise AssertionError('No provider or media URL generation')
    import httpx
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    async with SessionFactory() as s:
        before=await s.scalar(select(func.count()).select_from(Job))
        j=await direct.stage(s,uid,rid);again=await direct.stage(s,uid,rid)
        assert j['id']==again['id'] and j['login_mode']=='INSTAGRAM_LOGIN'
        assert not j['execution_enabled'] and not j['media_exposure_enabled'] and not j['approval_recorded']
        assert j['remaining_gates'] and j['caption']=='تعليق صناعي فقط'
        assert 'private-token' not in str(j) and 'config_hash' not in str(j)
        assert await s.scalar(select(func.count()).select_from(Job))==before+1
        job=await s.get(Job,UUID(j['id']));assert job.connection_binding['review_id']==str(rid)
        await direct.validate_binding(s,job)
        await core.cancel_draft(s,job.id)
        assert (await direct.history(s,uid))['items'][0]['state']=='CANCELLED'

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['disabled','config','account','expired','stale-check'])
async def test_direct_binding_blocks_changed_connection_before_provider(config,monkeypatch,change):
    uid,rid=await setup(monkeypatch);p=Provider();p.graph_base='https://graph.instagram.com/v27.0'
    async with SessionFactory() as s:
        j=await direct.stage(s,uid,rid);conn=await s.get(Connection,1)
        if change=='disabled':conn.enabled=False
        if change=='config':conn.config_hash='changed'
        if change=='account':conn.account_id='999'
        if change=='expired':conn.token_expires_at=oauth.now()-timedelta(seconds=1)
        if change=='stale-check':conn.last_check_at=oauth.now()-timedelta(minutes=6)
        await s.commit()
        with pytest.raises(ValueError):await core.create_container(s,UUID(j['id']),provider=p,media_url='https://synthetic.example/a.jpg',media_sha256=DIGEST,authorized=True,public_publish_authorized=True,media_disclosure_authorized=True)
        assert not p.calls

@pytest.mark.asyncio
async def test_direct_stage_strict_owner_origin_no_authority_payload(config,monkeypatch):
    import httpx
    from app.main import app
    uid,rid=await setup(monkeypatch);base=f'{oauth.BASE}/materials/{uid}/execution-drafts'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as anon:
        assert (await anon.get(base)).status_code==401
        assert (await anon.post(base,json={'review_id':str(rid)})).status_code==401
    async with browser() as c:
        assert (await c.post(base,json={'review_id':str(rid),'authorized':True})).status_code==422
        assert (await c.post(base,json={'review_id':str(rid)},headers={'Origin':'https://other.invalid'})).status_code==403
        r=await c.post(base,json={'review_id':str(rid)});assert r.status_code==200,r.text
        assert r.headers['cache-control']=='no-store' and not r.json()['approval_recorded']
        assert (await c.post(base+'/'+r.json()['id']+'/publish',json={})).status_code==404
        assert (await c.post(base+'/'+r.json()['id']+'/cancel')).status_code==200

@pytest.mark.asyncio
async def test_direct_stage_no_fallback_and_stale_source(config,monkeypatch):
    uid,rid=await setup(monkeypatch)
    async with SessionFactory() as s:
        row=await s.get(PlatformCopyModel,(uid,'instagram'));row.version+=1;await s.commit()
        with pytest.raises(ValueError):await direct.stage(s,uid,rid)
        p=await review.preview(s,uid);assert p.get('login_mode') is None


@pytest.mark.asyncio
@pytest.mark.parametrize('flags',[{}, {'public_publish_authorized':True}, {'media_disclosure_authorized':True}])
async def test_direct_core_requires_separate_public_and_media_disclosure(config,monkeypatch,flags):
    uid,rid=await setup(monkeypatch);p=Provider();p.graph_base='https://graph.instagram.com/v27.0'
    async with SessionFactory() as s:
        j=await direct.stage(s,uid,rid)
        with pytest.raises(ValueError,match='disclosure'):await core.create_container(s,UUID(j['id']),provider=p,media_url='https://synthetic.example/a.jpg',media_sha256=DIGEST,authorized=True,**flags)
        assert not p.calls
