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
        r=await c.get('/instagram-media',params={'capability':token});assert r.status_code==404 # Unlinked legacy grant cannot disclose bytes
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await decisions.revoke(s,did) # No dispatch authority/link
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


@pytest.mark.asyncio
async def test_known_published_reconciles_after_decision_expiry_without_mutation(config,monkeypatch):
    from app.application import instagram_runtime as runtime,instagram_dispatch as dispatch
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        for row in (await s.execute(select(Dispatch))).scalars():row.state='CANCELLED'
        job=await s.get(Job,jid);job.state='PUBLISHED_ID_KNOWN';job.media_id='confirmed-media'
        s.add(Dispatch(execution_id=jid,decision_id=did,due_at=due,state='BLOCKED',updated_at=due));await s.commit()
    monkeypatch.setattr(decisions,'now',lambda:due+timedelta(minutes=20))
    async def forbidden(*a,**k):raise AssertionError('No publication decision or mutation replay')
    async def provider(*a,**k):return object()
    seen=[]
    async def reconcile(s,did,**kw):seen.append(did)
    monkeypatch.setattr(decisions,'validate',forbidden)
    monkeypatch.setattr(dispatch,'run',forbidden);monkeypatch.setattr(dispatch,'resume_media',forbidden)
    monkeypatch.setattr(execution,'verified_provider',provider);monkeypatch.setattr(dispatch,'reconcile',reconcile)
    async def refresh(*a):pass
    monkeypatch.setattr(execution,'refresh_due_binding',refresh)
    await runtime.process_approved();assert len(seen)==1

@pytest.mark.asyncio
async def test_history_and_exact_result_agree_through_decision_lifecycle(config,monkeypatch):
    from app.application import instagram_dispatch as dispatch
    from app.infrastructure.database.models import InstagramPublishDecisionModel as Decision
    uid,rid=await setup(monkeypatch)
    monkeypatch.setenv('RAILWAY_PUBLIC_DOMAIN','synthetic.up.railway.app')
    async with SessionFactory() as s:j=await execution.stage(s,uid,rid)
    base=f'/api/connections/instagram/materials/{uid}/execution-drafts/{j["id"]}'
    async with browser() as c:
        async def compare():
            history=(await c.get(base.rsplit('/',1)[0])).json()
            item=next(i for i in history['items'] if i['id']==j['id'])
            exact=(await c.get(base+'/result')).json()
            assert item==exact
            assert history['execution_enabled']==any(i['execution_enabled'] for i in history['items'])
            return exact
        first=await compare()
        assert first['can_propose'] and not first['approval_recorded']
        due=decisions.now()+timedelta(minutes=2)
        p=dict(due_at=due.isoformat(),timezone_name='Asia/Riyadh')
        proposal=(await c.post(base+'/proposal',json=p)).json()
        approved=await c.post(base+'/approve',json={**p,'decision_hash':proposal['decision_hash'],
            'exact_words_approved':True,'public_post_approved':True,'media_disclosure_approved':True})
        assert approved.status_code==200
        row=await compare()
        assert row['dispatch_state']=='PENDING' and row['approval_recorded'] and row['execution_enabled']
        assert not row['can_propose'] and not row['remaining_gates']
        async with SessionFactory() as s:
            d=(await s.execute(select(Dispatch).where(Dispatch.execution_id==UUID(j['id'])))).scalar_one()
            decision=await s.get(Decision,d.decision_id);decision.expires_at=decisions.now()-timedelta(minutes=1)
            await s.commit()
        row=await compare()
        assert row['approval_expired'] and not row['execution_enabled'] and row['state']=='DRAFT'
        async with SessionFactory() as s:
            d=(await s.execute(select(Dispatch).where(Dispatch.execution_id==UUID(j['id'])))).scalar_one()
            decision=await s.get(Decision,d.decision_id);decision.expires_at=decisions.now()+timedelta(minutes=10);decision.state='REVOKED'
            await s.commit()
        row=await compare()
        assert row['dispatch_state']=='PENDING' and row['decision_state']=='REVOKED'
        assert not row['approval_expired'] and not row['execution_enabled'] and not row['approval_recorded']
        async with SessionFactory() as s:
            job=await s.get(Job,UUID(j['id']));job.state='PUBLISHED';job.media_id='synthetic-media';job.permalink='https://www.instagram.com/reel/Synthetic123/'
            d=(await s.execute(select(Dispatch).where(Dispatch.execution_id==job.id))).scalar_one();d.state='PUBLISHED'
            decision=await s.get(Decision,d.decision_id);decision.expires_at=decisions.now()-timedelta(minutes=1);decision.state='APPROVED'
            await s.commit()
        row=await compare()
        assert row['state']=='PUBLISHED' and row['approval_recorded'] and not row['execution_enabled']
        assert row['permalink'].endswith('/Synthetic123/')
        await c.post(base+'/revoke')
        row=await compare()
        assert row['decision_state']=='REVOKED' and not row['approval_recorded']
        assert row['state']=='PUBLISHED' and row['permalink'].endswith('/Synthetic123/')

@pytest.mark.asyncio
async def test_dispatch_database_constraints_and_timezone_types():
    from sqlalchemy import inspect
    from app.infrastructure.database.session import engine
    async with engine.connect() as c:
        def schema(conn):
            i=inspect(conn)
            return i.get_unique_constraints('instagram_dispatches'),i.get_foreign_keys('instagram_dispatches'),i.get_columns('instagram_dispatches'),i.get_columns('instagram_publish_decisions')
        unique,fks,dispatch_columns,decision_columns=await c.run_sync(schema)
    assert any(x['column_names']==['execution_id'] for x in unique)
    assert any(x['constrained_columns']==['decision_id'] and x['referred_table']=='instagram_publish_decisions' for x in fks)
    for columns,name in [(dispatch_columns,'due_at'),(dispatch_columns,'updated_at'),(decision_columns,'expires_at')]:
        col=next(x for x in columns if x['name']==name)
        assert col['type'].timezone is True and col['nullable'] is False

@pytest.mark.asyncio
async def test_revoked_pending_dispatch_cannot_claim_or_send(config,monkeypatch):
    from app.application import instagram_dispatch as dispatch,instagram_runtime as runtime
    from app.infrastructure.database.models import InstagramPublishDecisionModel as Decision
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        for row in (await s.execute(select(Dispatch))).scalars():row.state='CANCELLED'
        d=Dispatch(execution_id=jid,decision_id=did,due_at=due,state='PENDING',updated_at=due);s.add(d)
        decision=await s.get(Decision,did);decision.state='REVOKED'
        await s.commit();dispatch_id=d.id
    monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
    calls=[]
    class ForbiddenProvider:
        account_id='100'
        async def create_container(self,**kw):calls.append('send');raise AssertionError('No revoked send')
    def forbidden_url(*a):calls.append('grant');raise AssertionError('No revoked media grant')
    async with SessionFactory() as s:
        with pytest.raises(ValueError,match='revoked'):
            await dispatch.run(s,dispatch_id,provider=ForbiddenProvider(),grant_url_factory=forbidden_url,runtime_enabled=True)
        await s.rollback()
        row=await s.get(Dispatch,dispatch_id);assert row.state=='PENDING'
    async def forbidden_provider(*a,**kw):calls.append('provider');raise AssertionError('No revoked provider construction')
    monkeypatch.setattr(execution,'verified_provider',forbidden_provider)
    await runtime.process_approved()
    assert calls==[]
