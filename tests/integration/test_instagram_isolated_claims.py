"""Protocol-only synthetic controls, never seeded from real dispatches."""
from datetime import timedelta
from uuid import uuid4,UUID
import asyncio
import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramIsolatedControlModel as Control,InstagramIsolatedClaimModel as Claim
from app.application import instagram_isolated_claims as flow

async def setup():
    did=uuid4()
    async with SessionFactory() as s:
        s.add(Control(dispatch_id=did,generation=0,version=0,revoked=False,pins_hash='a'*64,connection_generation='b'*64,
            decision_expires_at=flow.now()+timedelta(hours=1),grant_expires_at=flow.now()+timedelta(minutes=15),grant_active=True));await s.commit()
    return did

async def acquire(did,**kw):
    defaults=dict(kind='WRITE',step='CREATE_CONTAINER',request_key=str(uuid4()),worker_id='worker-exact-instance',ownership_token=flow.token(),expected_generation=0,expected_version=0,pins_hash='a'*64,connection_generation='b'*64)
    defaults.update(kw)
    async with SessionFactory() as s:r=await flow.acquire(s,did,**defaults)
    return r,defaults

async def finish(r,kw,**more):
    args=dict(ownership_token=kw['ownership_token'],worker_id=kw['worker_id'],expected_claim_version=0,outcome='CONTAINER_KNOWN');args.update(more)
    async with SessionFactory() as s:return await flow.finish(s,UUID(r['id']),**args)

@pytest.mark.asyncio
async def test_claim_exact_step_forever_unique_and_no_token_serialization():
    did=await setup();r,kw=await acquire(did)
    assert kw['ownership_token'] not in str(r) and 'token_hash' not in r
    async with SessionFactory() as s:assert (await flow.acquire(s,did,**kw))['id']==r['id']
    await finish(r,kw)
    with pytest.raises(ValueError):await acquire(did,expected_version=2)
    pub,pkw=await acquire(did,step='PUBLISH',expected_version=2)
    done=await finish(pub,pkw,outcome='PUBLISHED');assert done['result']['outcome']=='PUBLISHED'
    with pytest.raises(ValueError):await acquire(did,step='PUBLISH',expected_version=4)

@pytest.mark.asyncio
async def test_two_live_workers_and_db_partial_unique_fence():
    did=await setup();results=await asyncio.gather(acquire(did),acquire(did),return_exceptions=True)
    assert sum(isinstance(v,tuple) for v in results)==1
    async with SessionFactory() as s:
        s.add(Claim(dispatch_id=did,request_key=str(uuid4()),request_hash='c'*64,token_hash=flow.digest(flow.token()),kind='WRITE',write_step='PUBLISH',state='ACTIVE',generation=0,control_version=1,version=0,worker_id='other',result={},created_at=flow.now()))
        with pytest.raises(DBAPIError):await s.commit()

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['revoked','grant','grant-expired','decision-expired','connection','pins'])
async def test_gate_rechecks_all_binding_and_expiry_inputs(change):
    did=await setup()
    async with SessionFactory() as s:
        c=await s.get(Control,did)
        if change=='revoked':c.revoked=True
        if change=='grant':c.grant_active=False
        if change=='grant-expired':c.grant_expires_at=flow.now()-timedelta(seconds=1)
        if change=='decision-expired':c.decision_expires_at=flow.now()-timedelta(seconds=1)
        if change=='connection':c.connection_generation='c'*64
        if change=='pins':c.pins_hash='c'*64
        await s.commit()
    with pytest.raises(ValueError):await acquire(did)

@pytest.mark.asyncio
async def test_revoke_before_claim_prevents_write_after_claim_is_truthfully_in_flight():
    did=await setup()
    async with SessionFactory() as s:r=await flow.revoke(s,did,expected_generation=0,expected_version=0)
    assert r['outcome']=='ACK_STOPPED_BEFORE_WRITE'
    with pytest.raises(ValueError):await acquire(did,expected_generation=1,expected_version=1)
    did=await setup();r,kw=await acquire(did)
    async with SessionFactory() as s:stopped=await flow.revoke(s,did,expected_generation=0,expected_version=1)
    assert stopped['outcome']=='REQUESTED_IN_FLIGHT'
    done=await finish(r,kw);assert done['result']['revoked_after_claim']
    with pytest.raises(ValueError):await acquire(did,step='PUBLISH',expected_generation=1,expected_version=3)

@pytest.mark.asyncio
async def test_unknown_never_replays_and_recovery_refuses_unverified_attestation():
    did=await setup();r,kw=await acquire(did);await finish(r,kw,outcome='UNKNOWN')
    with pytest.raises(ValueError):await acquire(did,expected_version=2)
    with pytest.raises(ValueError):await flow.recover(worker_confirmed_stopped=True,log_line='claimed stopped')

@pytest.mark.asyncio
async def test_read_late_result_superseded_by_new_write_and_backoff_persisted():
    did=await setup();r,kw=await acquire(did,kind='READ',step=None)
    write,wkw=await acquire(did,expected_version=1)
    stale=await finish(r,kw,outcome='READ_CONFIRMED');assert stale['state']=='SUPERSEDED'
    await finish(write,wkw,outcome='UNKNOWN')
    read,rkw=await acquire(did,kind='READ',step=None,expected_version=4)
    await finish(read,rkw,outcome='READ_RATE_LIMITED',retry_after_seconds=300)
    with pytest.raises(ValueError):await acquire(did,kind='READ',step=None,expected_version=6)

@pytest.mark.asyncio
async def test_claim_owner_and_version_cannot_be_forged_or_late_overwritten():
    did=await setup();r,kw=await acquire(did)
    with pytest.raises(ValueError):await finish(r,kw,ownership_token=flow.token())
    with pytest.raises(ValueError):await finish(r,kw,worker_id='not-the-worker')
    with pytest.raises(ValueError):await finish(r,kw,expected_claim_version=1)
    await finish(r,kw)
    with pytest.raises(ValueError):await finish(r,kw)

async def stop(items,key=None,**kw):
    args=dict(request_key=key or str(uuid4()),batch_id=uuid4(),snapshot_hash='d'*64,action='STOP_REMAINING',items=items);args.update(kw)
    async with SessionFactory() as s:r=await flow.stop_batch(s,**args)
    return r,args

@pytest.mark.asyncio
async def test_mixed_exact_stop_receipts_and_retry_scope_does_not_expand():
    published=await setup();p,pk=await acquire(published);await finish(p,pk)
    p,pk=await acquire(published,step='PUBLISH',expected_version=2);await finish(p,pk,outcome='PUBLISHED')
    unknown=await setup();u,uk=await acquire(unknown);await finish(u,uk,outcome='UNKNOWN')
    pending=await setup();active=await setup();a,ak=await acquire(active)
    items=[dict(dispatch_id=published,generation=0,version=4),dict(dispatch_id=unknown,generation=0,version=2),dict(dispatch_id=pending,generation=0,version=0),dict(dispatch_id=active,generation=0,version=1)]
    r,args=await stop(items);assert {e['outcome'] for e in r['events']}=={'ALREADY_PUBLISHED','ALREADY_UNKNOWN','ACK_STOPPED_BEFORE_WRITE','REQUESTED_IN_FLIGHT'}
    await finish(a,ak,outcome='STOPPED_WITHOUT_WRITE')
    async with SessionFactory() as s:again=await flow.stop_batch(s,**args)
    assert again['scope']==r['scope'] and len(again['events'])==5
    args['items']=items[:-1]
    with pytest.raises(ValueError):
        async with SessionFactory() as s:await flow.stop_batch(s,**args)

@pytest.mark.asyncio
async def test_stop_failure_stale_foreign_duplicate_no_partial_changes():
    one=await setup();two=await setup()
    for items in [[dict(dispatch_id=one,generation=0,version=0),dict(dispatch_id=two,generation=1,version=0)],
                  [dict(dispatch_id=one,generation=0,version=0),dict(dispatch_id=uuid4(),generation=0,version=0)],
                  [dict(dispatch_id=one,generation=0,version=0)]*2]:
        with pytest.raises(ValueError):await stop(items)
        async with SessionFactory() as s:assert not (await s.get(Control,one)).revoked

@pytest.mark.asyncio
async def test_stop_commit_failure_rolls_back_and_audit_is_db_immutable(monkeypatch):
    from sqlalchemy import event,update
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.infrastructure.database.models import InstagramIsolatedStopModel as Stop
    did=await setup()
    def fail(*a):raise ValueError('Injected receipt insert failure')
    event.listen(flow.StopEvent,'before_insert',fail)
    try:
        with pytest.raises(ValueError):await stop([dict(dispatch_id=did,generation=0,version=0)])
    finally:event.remove(flow.StopEvent,'before_insert',fail)
    async with SessionFactory() as s:assert not (await s.get(Control,did)).revoked
    r,args=await stop([dict(dispatch_id=did,generation=0,version=0)])
    async with SessionFactory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(update(Stop).where(Stop.id==UUID(r['id'])).values(scope_hash='f'*64));await s.commit()

@pytest.mark.asyncio
async def test_reconcile_unique_active_and_revoked_read_does_not_restore_permission():
    did=await setup();r,kw=await acquire(did,kind='READ',step=None)
    with pytest.raises(ValueError):await acquire(did,kind='READ',step=None,expected_version=1)
    async with SessionFactory() as s:await flow.revoke(s,did,expected_generation=0,expected_version=1)
    stale=await finish(r,kw,outcome='READ_CONFIRMED');assert stale['state']=='SUPERSEDED'
    read,rkw=await acquire(did,kind='READ',step=None,expected_generation=1,expected_version=3)
    await finish(read,rkw,outcome='READ_CONFIRMED')
    with pytest.raises(ValueError):await acquire(did,expected_generation=1,expected_version=5)

@pytest.mark.asyncio
async def test_stop_claim_serializes_with_independent_connection_lock():
    did=await setup()
    async with SessionFactory() as locker:
        async with locker.begin():
            await flow.locked(locker,did)
            with pytest.raises(DBAPIError):await acquire(did)
    r,kw=await acquire(did);assert r['state']=='ACTIVE'

@pytest.mark.asyncio
async def test_publish_cannot_race_create_or_skip_known_container():
    did=await setup()
    with pytest.raises(ValueError):await acquire(did,step='PUBLISH')
    r,kw=await acquire(did)
    with pytest.raises(ValueError):await acquire(did,step='PUBLISH',expected_version=1)
    with pytest.raises(ValueError):await finish(r,kw,outcome='PUBLISHED')
    await finish(r,kw,outcome='DEFINITE_REJECTION')
    with pytest.raises(ValueError):await acquire(did,step='PUBLISH',expected_version=2)
    with pytest.raises(ValueError):await acquire(did,expected_version=2)

@pytest.mark.asyncio
async def test_second_step_expiry_and_rotation_are_rechecked():
    for change in ['grant','decision','connection','pins']:
        did=await setup();r,kw=await acquire(did);await finish(r,kw)
        async with SessionFactory() as s:
            c=await s.get(Control,did)
            if change=='grant':c.grant_expires_at=flow.now()-timedelta(seconds=1)
            if change=='decision':c.decision_expires_at=flow.now()-timedelta(seconds=1)
            if change=='connection':c.connection_generation='e'*64
            if change=='pins':c.pins_hash='e'*64
            await s.commit()
        with pytest.raises(ValueError):await acquire(did,step='PUBLISH',expected_version=2)

@pytest.mark.asyncio
async def test_duplicate_ack_concurrency_appends_only_one_event():
    did=await setup();r,kw=await acquire(did)
    receipt,args=await stop([dict(dispatch_id=did,generation=0,version=1)])
    results=await asyncio.gather(finish(r,kw,outcome='UNKNOWN'),finish(r,kw,outcome='UNKNOWN'),return_exceptions=True)
    assert sum(isinstance(v,dict) for v in results)==1
    async with SessionFactory() as s:again=await flow.stop_batch(s,**args)
    assert [e['sequence'] for e in again['events']]==[0,1]

@pytest.mark.asyncio
async def test_commit_failure_is_atomic_not_only_insert_failure(monkeypatch):
    from sqlalchemy import event,func
    from sqlalchemy.orm import Session
    did=await setup()
    async with SessionFactory() as s:before=await s.scalar(select(func.count()).select_from(flow.Stop))
    def fail(*a):raise ValueError('Injected final commit failure')
    event.listen(Session,'before_commit',fail)
    try:
        with pytest.raises(ValueError):await stop([dict(dispatch_id=did,generation=0,version=0)])
    finally:event.remove(Session,'before_commit',fail)
    async with SessionFactory() as s:
        assert not (await s.get(Control,did)).revoked
        assert await s.scalar(select(func.count()).select_from(flow.Stop))==before

@pytest.mark.asyncio
async def test_module_is_unregistered_and_cannot_construct_provider_or_production_dispatch(monkeypatch):
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    for path in (root/'app').rglob('*.py'):
        if path.name in {'instagram_isolated_claims.py','instagram_production_fence.py','instagram_fenced_media_status.py','instagram_fenced_worker.py','models.py'}:continue
        assert 'instagram_isolated_claims' not in path.read_text()
    import httpx
    def forbidden(*a,**kw):raise AssertionError('Network forbidden')
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    did=await setup();r,kw=await acquire(did)
    await finish(r,kw,outcome='UNKNOWN')
    assert not r['execution_enabled']
