"""Synthetic atomic first-grant/Stop initialization, no registered runtime."""
import asyncio
from uuid import uuid4
import pytest
from sqlalchemy import select,delete,event,func
from sqlalchemy.orm import Session
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramMediaGrantModel as Grant,InstagramIsolatedClaimModel as Claim,InstagramIsolatedControlModel as Control,InstagramProductionFenceModel as Link,InstagramDispatchModel as Dispatch,InstagramPublishDecisionModel as Decision,InstagramIsolatedStopModel as Stop
from app.application import instagram_production_fence as flow,instagram_isolated_claims as claims,instagram_media_grants as grants
from tests.integration.test_instagram_write_authority import setup
from tests.integration.test_instagram_execution_core import private_storage
from tests.integration.test_instagram_oauth import config

async def pending(monkeypatch):
    ids=await setup(monkeypatch)
    async with SessionFactory() as s:
        await s.execute(delete(Grant).where(Grant.id==ids[3]));await s.commit()
    return ids

async def counts():
    async with SessionFactory() as s:return [await s.scalar(select(func.count()).select_from(m))for m in (Grant,Control,Link,Claim,Stop)]

async def first(ids):
    async with SessionFactory() as s:return await flow.first_grant_and_claim(s,ids[1],request_key=str(uuid4()),worker_id='worker-first-grant',ownership_token=claims.token())

async def stop(ids,key=None):
    async with SessionFactory() as s:return await flow.stop_dispatch(s,ids[1],request_key=key or str(uuid4()))

@pytest.mark.asyncio
async def test_first_grant_control_link_claim_atomic(config,monkeypatch):
    ids=await pending(monkeypatch);before=await counts();result,token=await first(ids)
    assert len(token)==43 and await counts()==[a+b for a,b in zip(before,[1,1,1,1,0])]
    async with SessionFactory() as s:
        link=await s.get(Link,ids[1]);g=await s.get(Grant,link.grant_id)
        assert grants.digest(token)==g.capability_hash and result['grant_id']==str(g.id)
    with pytest.raises(ValueError):await first(ids)

@pytest.mark.asyncio
@pytest.mark.parametrize('model',[Grant,Control,Link,Claim,Session])
async def test_any_failure_rolls_back_all(config,monkeypatch,model):
    ids=await pending(monkeypatch);before=await counts()
    def fail(*a):raise ValueError('Synthetic atomic failure')
    name='before_commit'if model is Session else 'before_insert'
    event.listen(model,name,fail)
    try:
        with pytest.raises(ValueError):await first(ids)
    finally:event.remove(model,name,fail)
    assert await counts()==before

@pytest.mark.asyncio
async def test_preclaim_stop_without_grant_never_mints_capability(config,monkeypatch):
    ids=await pending(monkeypatch);before=await counts();key=str(uuid4());r=await stop(ids,key)
    assert r['events'][0]['outcome']=='ACK_STOPPED_BEFORE_WRITE'
    assert await counts()==[a+b for a,b in zip(before,[0,1,1,0,1])]
    async with SessionFactory() as s:
        assert (await s.get(Link,ids[1])).grant_id is None
        assert (await s.get(Control,ids[1])).revoked
        assert (await s.get(Dispatch,ids[1])).state=='CANCELLED'
        assert (await s.get(Decision,ids[2])).state=='REVOKED'
    assert await stop(ids,key)==r
    with pytest.raises(ValueError):await first(ids)

@pytest.mark.asyncio
async def test_preclaim_stop_existing_grant_revokes_without_claim(config,monkeypatch):
    ids=await setup(monkeypatch);before=await counts();await stop(ids)
    assert await counts()==[a+b for a,b in zip(before,[0,1,1,0,1])]
    async with SessionFactory() as s:assert (await s.get(Grant,ids[3])).state=='REVOKED'

@pytest.mark.asyncio
async def test_first_grant_vs_stop_one_fence(config,monkeypatch):
    ids=await pending(monkeypatch)
    results=await asyncio.gather(first(ids),stop(ids),return_exceptions=True)
    assert any(not isinstance(r,Exception)for r in results)
    # Whichever wins, a subsequent Stop must produce terminal revocation and no retry.
    await stop(ids)
    async with SessionFactory() as s:
        assert (await s.get(Control,ids[1])).revoked
        assert (await s.get(Decision,ids[2])).state=='REVOKED'
        assert len(list(await s.scalars(select(Claim).where(Claim.dispatch_id==ids[1]))))<=1
    with pytest.raises(ValueError):await first(ids)

@pytest.mark.asyncio
async def test_stop_initialization_commit_failure_no_partial_state(config,monkeypatch):
    ids=await pending(monkeypatch);before=await counts()
    def fail(*a):raise ValueError('Synthetic Stop failure')
    event.listen(Session,'before_commit',fail)
    try:
        with pytest.raises(ValueError):await stop(ids)
    finally:event.remove(Session,'before_commit',fail)
    assert await counts()==before
    async with SessionFactory() as s:
        assert (await s.get(Dispatch,ids[1])).state=='PENDING'
        assert (await s.get(Decision,ids[2])).state=='APPROVED'

@pytest.mark.asyncio
async def test_expired_revoked_authority_still_stoppable(config,monkeypatch):
    from datetime import timedelta
    from app.application import instagram_publish_decisions as decisions
    ids=await pending(monkeypatch)
    monkeypatch.setattr(decisions,'now',lambda:ids[4]+timedelta(hours=1))
    assert (await stop(ids))['events'][0]['outcome']=='ACK_STOPPED_BEFORE_WRITE'

@pytest.mark.asyncio
async def test_first_grant_failed_authority_leaves_no_capability(config,monkeypatch):
    from app.infrastructure.database.models import DistributionSelectionModel as Selection,InstagramExecutionModel as Job
    ids=await pending(monkeypatch);before=await counts()
    async with SessionFactory() as s:
        job=await s.get(Job,ids[0]);(await s.get(Selection,job.artifact_id)).platforms=['facebook'];await s.commit()
    with pytest.raises(ValueError):await first(ids)
    assert await counts()==before

@pytest.mark.asyncio
async def test_two_first_grant_workers_never_two_capabilities(config,monkeypatch):
    ids=await pending(monkeypatch);before=await counts()
    results=await asyncio.gather(first(ids),first(ids),return_exceptions=True)
    assert sum(isinstance(r,tuple)for r in results)==1
    assert await counts()==[a+b for a,b in zip(before,[1,1,1,1,0])]
