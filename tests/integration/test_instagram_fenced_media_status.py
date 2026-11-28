"""Repeated media waiting uses READ only, no provider traffic."""
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramIsolatedClaimModel as Claim
from app.application import instagram_fenced_media_status as flow,instagram_production_fence as fence,instagram_isolated_claims as claims,instagram_publish_decisions as decisions
from tests.integration.test_instagram_production_fence import claim,stop
from tests.integration.test_instagram_write_authority import setup
from tests.integration.test_instagram_execution_core import private_storage
from tests.integration.test_instagram_oauth import config

async def known(monkeypatch):
    ids=await setup(monkeypatch);token=claims.token();r=await claim(ids,ownership_token=token)
    async with SessionFactory() as s:
        await fence.finish_create(s,ids[1],claim_id=UUID(r['id']),ownership_token=token,worker_id='exact-worker-instance',expected_claim_version=0,outcome='CONTAINER_KNOWN',container_id='200')
    return ids

async def read(ids,status):
    token=claims.token();worker='status-worker';key=str(uuid4())
    async with SessionFactory() as s:r=await flow.claim_status(s,ids[1],request_key=key,worker_id=worker,ownership_token=token)
    async with SessionFactory() as s:
        await flow.finish_status(s,ids[1],claim_id=UUID(r['id']),worker_id=worker,ownership_token=token,expected_claim_version=0,status=status)
    return UUID(r['id'])

async def publish(ids,observed):
    async with SessionFactory() as s:
        return await flow.claim_publish(s,ids[1],status_claim_id=observed,request_key=str(uuid4()),worker_id='publisher',ownership_token=claims.token())

async def publish_count(ids):
    async with SessionFactory() as s:return await s.scalar(select(func.count()).select_from(Claim).where(Claim.dispatch_id==ids[1],Claim.write_step=='PUBLISH'))

@pytest.mark.asyncio
async def test_repeated_in_progress_reads_consume_zero_publish_claims_then_one_ready(config,monkeypatch):
    ids=await known(monkeypatch)
    for n in range(3):
        monkeypatch.setattr(decisions,'now',lambda n=n:ids[4]+timedelta(seconds=2+61*n))
        # Protocol clock is the same production clock in this integrated test.
        monkeypatch.setattr(claims,'now',decisions.now)
        observed=await read(ids,'IN_PROGRESS')
        with pytest.raises(ValueError):await publish(ids,observed)
        assert await publish_count(ids)==0
    monkeypatch.setattr(decisions,'now',lambda:ids[4]+timedelta(seconds=186));monkeypatch.setattr(claims,'now',decisions.now)
    observed=await read(ids,'FINISHED');r=await publish(ids,observed)
    assert r['step']=='PUBLISH' and await publish_count(ids)==1
    with pytest.raises(ValueError):await publish(ids,observed)

@pytest.mark.asyncio
async def test_stop_between_finished_read_and_publish_blocks_post_claim(config,monkeypatch):
    ids=await known(monkeypatch);monkeypatch.setattr(claims,'now',decisions.now)
    observed=await read(ids,'FINISHED');await stop(ids)
    with pytest.raises(ValueError):await publish(ids,observed)
    assert await publish_count(ids)==0

@pytest.mark.asyncio
async def test_read_after_stop_cannot_restore_write_permission(config,monkeypatch):
    ids=await known(monkeypatch);await stop(ids);monkeypatch.setattr(claims,'now',decisions.now)
    observed=await read(ids,'FINISHED')
    with pytest.raises(ValueError):await publish(ids,observed)
    assert await publish_count(ids)==0

@pytest.mark.asyncio
async def test_read_backoff_is_persisted_and_stale_finished_cannot_publish(config,monkeypatch):
    ids=await known(monkeypatch);monkeypatch.setattr(claims,'now',decisions.now)
    observed=await read(ids,'FINISHED')
    with pytest.raises(ValueError):await read(ids,'IN_PROGRESS')
    monkeypatch.setattr(decisions,'now',lambda:ids[4]+timedelta(seconds=70));monkeypatch.setattr(claims,'now',decisions.now)
    with pytest.raises(ValueError):await publish(ids,observed)
    assert await publish_count(ids)==0

@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',['PUBLISHED','UNKNOWN','STOPPED_WITHOUT_WRITE'])
async def test_publish_owner_result_after_stop_retains_truth_and_no_replay(config,monkeypatch,outcome):
    ids=await known(monkeypatch);monkeypatch.setattr(claims,'now',decisions.now)
    observed=await read(ids,'FINISHED');token=claims.token()
    async with SessionFactory() as s:
        r=await flow.claim_publish(s,ids[1],status_claim_id=observed,request_key=str(uuid4()),worker_id='publisher',ownership_token=token)
    key=str(uuid4());await stop(ids,key)
    args=dict(claim_id=UUID(r['id']),worker_id='publisher',ownership_token=token,expected_claim_version=0,outcome=outcome,media_id='300'if outcome=='PUBLISHED'else None)
    async with SessionFactory() as s:done=await flow.finish_publish(s,ids[1],**args)
    assert done['result']['revoked_after_claim']
    receipt=await stop(ids,key);assert len(receipt['events'])==2 and receipt['events'][1]['outcome']==outcome
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await flow.finish_publish(s,ids[1],**args)
    with pytest.raises(ValueError):await publish(ids,observed)
    assert await publish_count(ids)==1

@pytest.mark.asyncio
async def test_stop_during_active_read_suppresses_late_readiness(config,monkeypatch):
    from app.infrastructure.database.models import InstagramProductionReadModel as Observation
    ids=await known(monkeypatch);monkeypatch.setattr(claims,'now',decisions.now);token=claims.token()
    async with SessionFactory() as s:r=await flow.claim_status(s,ids[1],request_key=str(uuid4()),worker_id='reader',ownership_token=token)
    await stop(ids)
    async with SessionFactory() as s:
        done=await flow.finish_status(s,ids[1],claim_id=UUID(r['id']),worker_id='reader',ownership_token=token,expected_claim_version=0,status='FINISHED')
        assert done['state']=='SUPERSEDED'
        assert await s.get(Observation,UUID(r['id'])) is None
    assert await publish_count(ids)==0

@pytest.mark.asyncio
async def test_foreign_finished_observation_rejected_and_publish_commit_failure_rolls_back(config,monkeypatch):
    from sqlalchemy.orm import Session
    from sqlalchemy import event
    ids=await known(monkeypatch);monkeypatch.setattr(claims,'now',decisions.now)
    # A nonexistent foreign claim cannot supply readiness for this dispatch.
    with pytest.raises(ValueError):await publish(ids,uuid4())
    observed=await read(ids,'FINISHED')
    def fail(*a):raise ValueError('Synthetic publish claim commit failure')
    event.listen(Session,'before_commit',fail)
    try:
        with pytest.raises(ValueError):await publish(ids,observed)
    finally:event.remove(Session,'before_commit',fail)
    assert await publish_count(ids)==0
    assert (await publish(ids,observed))['step']=='PUBLISH'

@pytest.mark.asyncio
async def test_wrong_read_owner_cannot_insert_ready_observation(config,monkeypatch):
    from app.infrastructure.database.models import InstagramProductionReadModel as Observation
    ids=await known(monkeypatch);token=claims.token();monkeypatch.setattr(claims,'now',decisions.now)
    async with SessionFactory() as s:r=await flow.claim_status(s,ids[1],request_key=str(uuid4()),worker_id='reader',ownership_token=token)
    async with SessionFactory() as s:
        with pytest.raises(ValueError):
            await flow.finish_status(s,ids[1],claim_id=UUID(r['id']),worker_id='not-reader',ownership_token=token,expected_claim_version=0,status='FINISHED')
    async with SessionFactory() as s:assert await s.get(Observation,UUID(r['id']))is None
    assert await publish_count(ids)==0
