"""Synthetic linkage and first-claim atomicity, no runtime/provider calls."""
import asyncio
from uuid import uuid4
from datetime import timedelta
import pytest
from sqlalchemy import select,func,event
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramProductionFenceModel as Link,InstagramIsolatedControlModel as Control,InstagramIsolatedClaimModel as Claim
from app.application import instagram_production_fence as flow,instagram_isolated_claims as claims
from tests.integration.test_instagram_write_authority import setup
from tests.integration.test_instagram_execution_core import private_storage
from tests.integration.test_instagram_oauth import config

async def counts():
    async with SessionFactory() as s:
        return [await s.scalar(select(func.count()).select_from(m)) for m in (Link,Control,Claim)]

async def claim(ids,**kw):
    args=dict(grant_id=ids[3],request_key=str(uuid4()),worker_id='exact-worker-instance',ownership_token=claims.token())
    args.update(kw)
    async with SessionFactory() as s:return await flow.claim_create(s,ids[1],**args)

@pytest.mark.asyncio
async def test_legacy_first_control_link_and_claim_one_commit(config,monkeypatch):
    ids=await setup(monkeypatch);before=await counts()
    r=await claim(ids);assert r['step']=='CREATE_CONTAINER' and not r['execution_enabled']
    assert await counts()==[n+1 for n in before]
    async with SessionFactory() as s:
        link=await s.get(Link,ids[1]);control=await s.get(Control,ids[1])
        assert link.execution_id==ids[0] and link.decision_id==ids[2] and link.grant_id==ids[3]
        assert control.version==1 and not control.revoked

@pytest.mark.asyncio
async def test_two_first_claim_workers_only_one_wins(config,monkeypatch):
    ids=await setup(monkeypatch);before=await counts()
    out=await asyncio.gather(claim(ids),claim(ids),return_exceptions=True)
    assert sum(isinstance(x,dict) for x in out)==1
    assert await counts()==[n+1 for n in before]

@pytest.mark.asyncio
@pytest.mark.parametrize('model',[Link,Claim])
async def test_initial_link_or_claim_insert_failure_rolls_back_control(config,monkeypatch,model):
    ids=await setup(monkeypatch);before=await counts()
    def fail(*a):raise ValueError('Synthetic atomic failure')
    event.listen(model,'before_insert',fail)
    try:
        with pytest.raises(ValueError):await claim(ids)
    finally:event.remove(model,'before_insert',fail)
    assert await counts()==before

@pytest.mark.asyncio
async def test_first_claim_commit_failure_rolls_back_everything(config,monkeypatch):
    from sqlalchemy.orm import Session
    ids=await setup(monkeypatch);before=await counts()
    def fail(*a):raise ValueError('Synthetic commit failure')
    event.listen(Session,'before_commit',fail)
    try:
        with pytest.raises(ValueError):await claim(ids)
    finally:event.remove(Session,'before_commit',fail)
    assert await counts()==before

@pytest.mark.asyncio
async def test_unowned_synthetic_control_cannot_be_promoted(config,monkeypatch):
    ids=await setup(monkeypatch)
    async with SessionFactory() as s:
        s.add(Control(dispatch_id=ids[1],generation=0,version=0,revoked=False,pins_hash='a'*64,
            connection_generation='b'*64,decision_expires_at=ids[4]+timedelta(minutes=15),
            grant_expires_at=ids[4]+timedelta(minutes=15),grant_active=True));await s.commit()
    before=await counts()
    with pytest.raises(ValueError):await claim(ids)
    assert await counts()==before

@pytest.mark.asyncio
async def test_publish_and_resume_cannot_consume_any_claim(config,monkeypatch):
    ids=await setup(monkeypatch);before=await counts()
    for _ in range(3):
        with pytest.raises(ValueError):await flow.claim_publish(None,ids[1],status='IN_PROGRESS')
    assert await counts()==before

@pytest.mark.asyncio
async def test_no_new_control_when_authority_fails(config,monkeypatch):
    from app.infrastructure.database.models import InstagramPublishDecisionModel as Decision
    ids=await setup(monkeypatch)
    async with SessionFactory() as s:
        (await s.get(Decision,ids[2])).state='REVOKED';await s.commit()
    before=await counts()
    with pytest.raises(ValueError):await claim(ids)
    assert await counts()==before

async def stop(ids,key=None):
    async with SessionFactory() as s:return await flow.stop_dispatch(s,ids[1],request_key=key or str(uuid4()))

@pytest.mark.asyncio
async def test_stop_active_create_is_requested_and_atomic_revocation(config,monkeypatch):
    from app.infrastructure.database.models import InstagramPublishDecisionModel as Decision,InstagramMediaGrantModel as Grant
    ids=await setup(monkeypatch);r=await claim(ids);key=str(uuid4());out=await stop(ids,key)
    assert out['events'][0]['outcome']=='REQUESTED_IN_FLIGHT'
    async with SessionFactory() as s:
        assert (await s.get(Control,ids[1])).revoked
        assert (await s.get(Decision,ids[2])).state=='REVOKED'
        assert (await s.get(Grant,ids[3])).state=='REVOKED'
        assert (await s.get(Claim,__import__('uuid').UUID(r['id']))).state=='ACTIVE'
    assert await stop(ids,key)==out
    with pytest.raises(ValueError):await claim(ids)

@pytest.mark.asyncio
async def test_stop_commit_failure_rolls_back_fence_decision_grant_receipt(config,monkeypatch):
    from sqlalchemy.orm import Session
    from app.infrastructure.database.models import InstagramPublishDecisionModel as Decision,InstagramMediaGrantModel as Grant
    ids=await setup(monkeypatch);await claim(ids)
    def fail(*a):raise ValueError('Stop commit failure')
    event.listen(Session,'before_commit',fail)
    try:
        with pytest.raises(ValueError):await stop(ids)
    finally:event.remove(Session,'before_commit',fail)
    async with SessionFactory() as s:
        assert not (await s.get(Control,ids[1])).revoked
        assert (await s.get(Decision,ids[2])).state=='APPROVED'
        assert (await s.get(Grant,ids[3])).state=='ACTIVE'

@pytest.mark.asyncio
async def test_new_modules_have_no_runtime_or_route_consumers():
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]/'app'
    for path in [root/'main.py',*(root/'api').rglob('*.py')]:
        assert 'instagram_production_fence' not in path.read_text()
        assert 'instagram_write_authority' not in path.read_text()

@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',['CONTAINER_KNOWN','UNKNOWN','STOPPED_WITHOUT_WRITE'])
async def test_owner_cas_after_stop_appends_receipt_and_preserves_real_outcome(config,monkeypatch,outcome):
    from uuid import UUID
    from app.infrastructure.database.models import InstagramExecutionModel as Job,InstagramDispatchModel as Dispatch
    ids=await setup(monkeypatch);token=claims.token();r=await claim(ids,ownership_token=token);key=str(uuid4());await stop(ids,key)
    args=dict(claim_id=UUID(r['id']),ownership_token=token,worker_id='exact-worker-instance',expected_claim_version=0,outcome=outcome,container_id='200'if outcome=='CONTAINER_KNOWN'else None)
    async with SessionFactory() as s:done=await flow.finish_create(s,ids[1],**args)
    assert done['result']['revoked_after_claim']
    receipt=await stop(ids,key);assert len(receipt['events'])==2 and receipt['events'][1]['outcome']==outcome
    async with SessionFactory() as s:
        job=await s.get(Job,ids[0]);dispatch=await s.get(Dispatch,ids[1])
        if outcome=='CONTAINER_KNOWN':assert job.container_id=='200' and dispatch.state=='BLOCKED'
        if outcome=='UNKNOWN':assert job.state=='CREATE_UNKNOWN' and dispatch.state=='RECONCILE_ONLY'
        if outcome=='STOPPED_WITHOUT_WRITE':assert job.state==dispatch.state=='CANCELLED'
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await flow.finish_create(s,ids[1],**args)
    with pytest.raises(ValueError):await claim(ids)

@pytest.mark.asyncio
async def test_first_claim_invisible_to_other_connection_until_complete(config,monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    ids=await setup(monkeypatch);before=await counts();entered=asyncio.Event();release=asyncio.Event()
    original=AsyncSession.flush
    async def pause(self,*a,**kw):
        await original(self,*a,**kw)
        if any(isinstance(x,Link)for x in self.sync_session.identity_map.values()):
            entered.set();await release.wait()
    monkeypatch.setattr(AsyncSession,'flush',pause)
    task=asyncio.create_task(claim(ids))
    try:
        await asyncio.wait_for(entered.wait(),5)
        assert await counts()==before
    finally:release.set()
    await task;assert await counts()==[n+1 for n in before]
