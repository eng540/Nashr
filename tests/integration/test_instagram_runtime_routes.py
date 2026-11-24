from datetime import timedelta
from uuid import UUID
import httpx,pytest
from sqlalchemy import select
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job
from app.application import instagram_unified_execution as execution,instagram_publish_decisions as decisions,instagram_media_grants as grants
from tests.integration.test_instagram_oauth import config,browser
from tests.integration.test_instagram_unified_execution_drafts import setup
from tests.integration.test_instagram_unified_execution_gates import approved
from tests.integration.test_instagram_execution_core import private_storage,MEDIA

@pytest.mark.asyncio
async def test_owner_exact_decision_routes_and_no_automatic_approval(config,monkeypatch):
    uid,rid=await setup(monkeypatch);monkeypatch.setenv('RAILWAY_PUBLIC_DOMAIN','synthetic.up.railway.app')
    async with SessionFactory() as s:j=await execution.stage(s,uid,rid)
    base=f'/api/connections/instagram/materials/{uid}/execution-drafts/{j["id"]}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as anon:
        assert (await anon.post(base+'/proposal',json={})).status_code==401
    due=(decisions.now()+timedelta(minutes=2)).isoformat();payload=dict(due_at=due,timezone_name='Asia/Riyadh')
    async with browser() as c:
        assert (await c.post(base+'/proposal',json=payload,headers={'Origin':'https://other.invalid'})).status_code==403
        r=await c.post(base+'/proposal',json=payload);assert r.status_code==200,r.text
        assert r.json()['approval_recorded'] is False
        exact={**payload,'decision_hash':r.json()['decision_hash'],'exact_words_approved':True,'public_post_approved':True,'media_disclosure_approved':True}
        for field in ['exact_words_approved','public_post_approved','media_disclosure_approved']:
            assert (await c.post(base+'/approve',json={**exact,field:False})).status_code==409
        r=await c.post(base+'/approve',json=exact);assert r.status_code==200,r.text
        assert r.json()['state']=='PENDING'
        assert (await c.post(base+'/approve',json=exact)).json()['dispatch_id']==r.json()['dispatch_id']
        assert (await c.get(base+'/result')).json()['state']=='DRAFT'
        assert (await c.post(base+'/revoke')).json()['already_published_content_removed'] is False
        assert (await c.get(base+'/result')).json()['dispatch_state']=='CANCELLED'

@pytest.mark.asyncio
async def test_capability_anonymous_but_not_without_exact_secret(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1));g,token=await grants.mint(s,jid,did)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.get('/instagram-media')).status_code==404
        assert (await c.get('/instagram-media',params={'capability':'wrong'})).status_code==404
        r=await c.get('/instagram-media',params={'capability':token});assert r.status_code==200 and r.content==MEDIA
        assert r.headers['cache-control']=='no-store' and token not in str(r.headers)
    async with SessionFactory() as s:await decisions.revoke(s,did)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.get('/instagram-media',params={'capability':token})).status_code==404

@pytest.mark.asyncio
async def test_unknown_claim_never_automatically_scanned(config,monkeypatch):
    from app.application import instagram_runtime as runtime
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        row=Dispatch(execution_id=jid,decision_id=did,due_at=due,state='RECONCILE_ONLY',updated_at=due);s.add(row);await s.commit()
    def forbidden(*a,**k):raise AssertionError('No automatic unknown-outcome retry')
    monkeypatch.setattr(execution,'verified_provider',forbidden)
    monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
    # Isolate any older test dispatches.
    async with SessionFactory() as s:
        for row in (await s.execute(select(Dispatch).where(Dispatch.execution_id!=jid))).scalars():row.state='CANCELLED'
        await s.commit()
    await runtime.process_approved()

@pytest.mark.asyncio
async def test_redact_capability_before_logs():
    from app.infrastructure.connection_logging import redact
    assert 'sensitive' not in redact('GET /instagram-media?capability=sensitive HTTP/1.1')
