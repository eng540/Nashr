"""Real fenced individual worker with synthetic private rows/provider."""
import asyncio
from uuid import uuid4
from datetime import timedelta
import pytest
from sqlalchemy import select,func
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramIsolatedClaimModel as Claim,InstagramMediaGrantModel as Grant,InstagramProductionFenceModel as Link,InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job
from app.application import instagram_fenced_worker as worker,instagram_production_fence as fence,instagram_isolated_claims as claims,instagram_publish_decisions as decisions,instagram_media_grants as grants
from app.adapters.publishing.instagram import ContainerState,InstagramProviderError
from tests.integration.test_instagram_first_grant_stop import pending
from tests.integration.test_instagram_execution_core import private_storage,MEDIA
from tests.integration.test_instagram_oauth import config

class Provider:
    graph_base='https://graph.facebook.com/v27.0'
    account_id='100'
    def __init__(self):self.calls=[];self.status='FINISHED'
    async def create_container(self,**kw):self.calls.append('create');return '200'
    async def container_status(self,cid):self.calls.append('status');return ContainerState(cid,self.status)
    async def publish_claimed_container(self,cid):self.calls.append('post');return '300'
    async def publish_container(self,*a):raise AssertionError('Forbidden legacy publish')

async def run(ids,p):return await worker.run(ids[1],provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/media')
async def stop(ids):
    async with SessionFactory() as s:return await fence.stop_dispatch(s,ids[1],request_key=str(uuid4()))
async def writes(ids,step):
    async with SessionFactory() as s:return await s.scalar(select(func.count()).select_from(Claim).where(Claim.dispatch_id==ids[1],Claim.write_step==step))

@pytest.mark.asyncio
async def test_worker_exact_claimed_edges_and_final_cas(config,monkeypatch):
    ids=await pending(monkeypatch);p=Provider()
    assert (await run(ids,p)).state=='RESULT_KNOWN'
    assert p.calls==['create','status','post']
    assert await writes(ids,'CREATE_CONTAINER')==await writes(ids,'PUBLISH')==1
    with pytest.raises(ValueError):await run(ids,p)
    async with SessionFactory() as s:
        j=await s.get(Job,ids[0]);link=await s.get(Link,ids[1]);assert j.media_id=='300'
        assert (await s.get(Grant,link.grant_id)).state=='REVOKED'

@pytest.mark.asyncio
async def test_in_progress_reads_consume_zero_publish_then_one_finished(config,monkeypatch):
    ids=await pending(monkeypatch);p=Provider();p.status='IN_PROGRESS';await run(ids,p)
    for n in range(1,4):
        monkeypatch.setattr(claims,'now',lambda:ids[4]+timedelta(minutes=n*2))
        await worker.resume(ids[1],provider=p)
    assert await writes(ids,'PUBLISH')==0 and 'post'not in p.calls
    p.status='FINISHED';monkeypatch.setattr(claims,'now',lambda:ids[4]+timedelta(minutes=9))
    assert (await worker.resume(ids[1],provider=p)).state=='RESULT_KNOWN'
    assert p.calls.count('post')==1

@pytest.mark.asyncio
async def test_stop_between_finished_and_claim_no_post(config,monkeypatch):
    ids=await pending(monkeypatch)
    class Stopped(Provider):
        async def container_status(self,cid):
            self.calls.append('status');await stop(ids);return ContainerState(cid,'FINISHED')
    p=Stopped();await run(ids,p)
    assert p.calls==['create','status'] and await writes(ids,'PUBLISH')==0

@pytest.mark.asyncio
async def test_stop_inflight_publish_reports_late_truth(config,monkeypatch):
    ids=await pending(monkeypatch);receipts=[]
    class Late(Provider):
        async def publish_claimed_container(self,cid):
            self.calls.append('post');receipts.append(await stop(ids));return '300'
    p=Late();assert (await run(ids,p)).state=='RESULT_KNOWN'
    assert receipts[0]['events'][0]['outcome']=='REQUESTED_IN_FLIGHT'
    async with SessionFactory() as s:
        from app.infrastructure.database.models import InstagramIsolatedStopModel as Stop
        r=await s.get(Stop,__import__('uuid').UUID(receipts[0]['id']));receipt=await claims.stop_receipt(s,r)
        assert receipt['events'][1]['outcome']=='PUBLISHED'

@pytest.mark.asyncio
async def test_unknown_never_reposts_and_revokes_capability(config,monkeypatch):
    ids=await pending(monkeypatch)
    class Unknown(Provider):
        async def publish_claimed_container(self,cid):self.calls.append('post');raise InstagramProviderError('UNKNOWN',outcome_unknown=True)
    p=Unknown();assert (await run(ids,p)).state=='RECONCILE_ONLY'
    with pytest.raises(ValueError):await run(ids,p)
    assert p.calls.count('post')==1

@pytest.mark.asyncio
async def test_actual_media_delivery_uses_shared_fence_and_stop(config,monkeypatch):
    ids=await pending(monkeypatch);token=claims.token()
    async with SessionFactory() as s:r,cap=await fence.first_grant_and_claim(s,ids[1],request_key=str(uuid4()),worker_id='exact-worker',ownership_token=token)
    async with SessionFactory() as s:assert (await grants.read(s,cap))[0]==MEDIA
    await stop(ids)
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await grants.read(s,cap)

@pytest.mark.asyncio
async def test_permalink_reconciliation_read_only_after_stop(config,monkeypatch):
    ids=await pending(monkeypatch);p=Provider();await run(ids,p);await stop(ids)
    monkeypatch.setattr(claims,'now',lambda:ids[4]+timedelta(minutes=3))
    async def result(mid):
        p.calls.append('permalink');return dict(media_id=mid,account_id='100',permalink='https://www.instagram.com/p/SyntheticOnly/')
    p.published_media=result
    assert (await worker.reconcile(ids[1],provider=p)).state=='PUBLISHED'
    assert p.calls==['create','status','post','permalink']

@pytest.mark.asyncio
async def test_stop_during_permalink_supersedes_result_no_overwrite(config,monkeypatch):
    ids=await pending(monkeypatch);p=Provider();await run(ids,p)
    monkeypatch.setattr(claims,'now',lambda:ids[4]+timedelta(minutes=3))
    async def result(mid):
        await stop(ids);return dict(media_id=mid,account_id='100',permalink='https://www.instagram.com/p/SyntheticOnly/')
    p.published_media=result
    assert (await worker.reconcile(ids[1],provider=p)).state=='RESULT_KNOWN'
    async with SessionFactory() as s:assert not (await s.get(Job,ids[0])).permalink

@pytest.mark.asyncio
async def test_old_core_unified_bypass_rejected(config,monkeypatch):
    from app.application import instagram_execution as core
    ids=await pending(monkeypatch);p=Provider()
    async with SessionFactory() as s:
        with pytest.raises(ValueError,match='fence'):await core.create_container(s,ids[0],provider=p,media_url='https://synthetic.invalid',media_sha256='a'*64,authorized=True)
    assert p.calls==[]

@pytest.mark.asyncio
async def test_two_workers_one_committed_create(config,monkeypatch):
    ids=await pending(monkeypatch);p=Provider()
    results=await asyncio.gather(run(ids,p),run(ids,p),return_exceptions=True)
    assert any(not isinstance(r,Exception)for r in results)
    assert p.calls.count('create')==p.calls.count('post')==1

@pytest.mark.asyncio
async def test_rate_limit_persists_backoff_no_hidden_retry(config,monkeypatch):
    ids=await pending(monkeypatch)
    class Limited(Provider):
        async def container_status(self,cid):
            self.calls.append('status');raise InstagramProviderError('INSTAGRAM_RATE_LIMITED',retry_after_seconds=600)
    p=Limited();assert (await run(ids,p)).state=='WAITING_MEDIA'
    with pytest.raises(ValueError,match='backoff'):await worker.resume(ids[1],provider=p)
    assert p.calls==['create','status'] and await writes(ids,'PUBLISH')==0

@pytest.mark.asyncio
async def test_authenticated_http_stop_and_media_share_same_fence(config,monkeypatch):
    import httpx
    from app.main import app
    from tests.integration.test_instagram_oauth import browser
    ids=await pending(monkeypatch)
    async with SessionFactory() as s:
        receipt,cap=await fence.first_grant_and_claim(s,ids[1],request_key=str(uuid4()),worker_id='exact-worker',ownership_token=claims.token())
        uid=(await s.get(Job,ids[0])).artifact_id
    base=f'/api/connections/instagram/materials/{uid}/execution-drafts/{ids[0]}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as anon:
        assert (await anon.get('/instagram-media',params={'capability':cap})).content==MEDIA
        assert (await anon.post(base+'/revoke')).status_code==401
    async with browser() as c:
        r=await c.post(base+'/revoke');assert r.status_code==200
        data=r.json();assert data['stop_receipt']['events'][0]['outcome']=='REQUESTED_IN_FLIGHT'
        assert (await c.post(base+'/revoke')).json()==data
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as anon:
        assert (await anon.get('/instagram-media',params={'capability':cap})).status_code==404

@pytest.mark.asyncio
async def test_stop_before_claim_no_provider_or_grant(config,monkeypatch):
    ids=await pending(monkeypatch);await stop(ids);p=Provider()
    with pytest.raises(ValueError):await run(ids,p)
    assert not p.calls and await writes(ids,'CREATE_CONTAINER')==0

@pytest.mark.asyncio
async def test_stop_inflight_create_keeps_known_container_blocks_publish(config,monkeypatch):
    ids=await pending(monkeypatch)
    class Late(Provider):
        async def create_container(self,**kw):
            self.calls.append('create');await stop(ids);return '200'
    p=Late();await run(ids,p)
    assert p.calls==['create','status'] and await writes(ids,'PUBLISH')==0
    async with SessionFactory() as s:assert (await s.get(Job,ids[0])).container_id=='200'

@pytest.mark.asyncio
async def test_provider_result_commit_failure_cannot_repeat_post(config,monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    ids=await pending(monkeypatch)
    def fail(*a):raise ValueError('Synthetic result commit failure')
    class CommittedRemote(Provider):
        async def publish_claimed_container(self,cid):
            self.calls.append('post');event.listen(Session,'before_commit',fail);return '300'
    p=CommittedRemote()
    try:
        with pytest.raises(ValueError):await run(ids,p)
    finally:event.remove(Session,'before_commit',fail)
    with pytest.raises(ValueError):await worker.resume(ids[1],provider=p)
    assert p.calls.count('post')==1 and await writes(ids,'PUBLISH')==1
