"""Synthetic local PostgreSQL only. Never talks to Meta or starts a scheduler."""
import asyncio
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.exc import DBAPIError
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import (InstagramBatchDraftModel as Batch,
    InstagramExecutionModel as Job,InstagramPublishDecisionModel as Decision,
    InstagramDispatchModel as Dispatch,InstagramMediaGrantModel as Grant,
    DistributionSelectionModel as Selection,PlatformCopyModel as Copy,ArtifactModel as Artifact,
    InstagramConnectionModel as Connection,InstagramPlanDraftModel as Review)
from app.application import instagram_batch_decisions as flow,instagram_unified_execution as direct
from app.application import instagram_plan_review as review,instagram_oauth as oauth
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_instagram_unified_execution_drafts import connected
from tests.integration.test_instagram_execution_core import seed,private_storage
from tests.integration.test_instagram_oauth import config

async def batch_setup(monkeypatch,n=2):
    await connected(monkeypatch)
    items=[]
    for _ in range(n):
        uid,synthetic=await seed()
        async with SessionFactory() as s:
            (await s.get(Job,synthetic)).state='CANCELLED';await s.commit()
            p=await review.preview(s,uid,login_mode='UNIFIED')
            r=await review.save_draft(s,uid,preview_hash=p['preview_hash'],login_mode='UNIFIED')
            j=await direct.stage(s,uid,UUID(r['id']))
            a=await s.get(Artifact,uid)
            s.add(Selection(artifact_id=uid,platforms=['instagram','facebook'],source_fingerprint=source_fingerprint(a),saved_at=oauth.now()));await s.commit()
        items.append(dict(execution_id=j['id'],due_at=oauth.now()+timedelta(hours=1),timezone='Asia/Riyadh'))
    return items

async def stage(items):
    async with SessionFactory() as s:return await flow.stage(s,items,request_key=str(uuid4()))

async def approve(plan,**kw):
    flags=dict(authenticated_owner=True,exact_batch_approved=True,public_posts_approved=True,media_disclosures_approved=True,evidence_ref='trusted-message:synthetic-local-only')
    flags.update(kw)
    async with SessionFactory() as s:return await flow.approve(s,UUID(plan['id']),snapshot_hash=plan['snapshot_hash'],**flags)

async def counts(items):
    ids=[UUID(i['execution_id']) for i in items]
    async with SessionFactory() as s:
        return tuple([await s.scalar(select(func.count()).select_from(m).where(m.execution_id.in_(ids))) for m in [Decision,Dispatch,Grant]])

@pytest.mark.asyncio
async def test_private_stage_then_atomic_approval_idempotent(config,monkeypatch):
    items=await batch_setup(monkeypatch)
    import httpx
    def forbidden(*args,**kwargs):raise AssertionError('No provider call or public URL')
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    p=await stage(items)
    assert p['state']=='DRAFT' and not p['execution_enabled'] and not p['media_exposure_enabled']
    assert [i['execution_id'] for i in p['items']]==[i['execution_id'] for i in items]
    assert p['items'][0]['caption']=='تعليق صناعي فقط' and 'facebook' in p['items'][0]['selection_platforms']
    assert await counts(items)==(0,0,0)
    done=await approve(p);again=await approve(p)
    assert done['state']=='APPROVED' and done['decision_ids']==again['decision_ids']
    assert await counts(items)==(2,2,0)

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['copy','text','original','choice','choice-version','review','account','inspection','state','time','hash','authority','duplicate','empty-binding','kind'])
async def test_changed_or_invalid_later_entry_leaves_zero_runnable_rows(config,monkeypatch,change):
    items=await batch_setup(monkeypatch);p=await stage(items)
    async with SessionFactory() as s:
        job=await s.get(Job,UUID(items[-1]['execution_id']))
        if change=='copy':(await s.get(Copy,(job.artifact_id,'instagram'))).version+=1
        if change=='text':
            copy=await s.get(Copy,(job.artifact_id,'instagram'));copy.fields={**copy.fields,'description':'changed'}
        if change=='original':(await s.get(Artifact,job.artifact_id)).review_status='DRAFT'
        if change=='choice':(await s.get(Selection,job.artifact_id)).platforms=['facebook']
        if change=='choice-version':(await s.get(Selection,job.artifact_id)).saved_at+=timedelta(seconds=1)
        if change=='review':(await s.get(Review,UUID(job.connection_binding['review_id']))).state='CANCELLED'
        if change=='account':(await s.get(Connection,1)).account_id='999'
        if change=='inspection':job.media_sha256='b'*64
        if change=='state':job.state='CREATE_UNKNOWN'
        if change=='empty-binding':job.connection_binding={}
        if change=='kind':job.kind='VIDEO'
        if change=='duplicate':
            s.add(Decision(execution_id=job.id,snapshot_hash='a'*64,snapshot={},evidence_ref='synthetic-local',state='REVOKED',created_at=oauth.now(),expires_at=oauth.now()+timedelta(hours=1)))
        await s.commit()
    if change=='time':monkeypatch.setattr(flow.decisions,'now',lambda:items[0]['due_at']+timedelta(seconds=1))
    if change=='hash':p['snapshot_hash']='f'*64
    with pytest.raises(ValueError):await approve(p,**({'exact_batch_approved':False} if change=='authority' else {}))
    assert await counts(items)==((1,0,0) if change=='duplicate' else (0,0,0))
    async with SessionFactory() as s:assert (await s.get(Batch,UUID(p['id']))).state=='DRAFT'

@pytest.mark.asyncio
async def test_insert_failure_after_first_decision_rolls_back_everything(config,monkeypatch):
    items=await batch_setup(monkeypatch);p=await stage(items);calls=0
    def fail(mapper,connection,target):
        nonlocal calls
        calls+=1
        if calls==2:raise ValueError('Injected second decision storage failure')
    event.listen(Decision,'before_insert',fail)
    try:
        with pytest.raises(ValueError,match='Injected'):await approve(p)
    finally:event.remove(Decision,'before_insert',fail)
    assert calls==2 and await counts(items)==(0,0,0)
    assert (await approve(p))['state']=='APPROVED'

@pytest.mark.asyncio
async def test_overlapping_concurrent_batches_only_one_commits(config,monkeypatch):
    items=await batch_setup(monkeypatch);a=await stage(items);b=await stage(list(reversed(items)))
    results=await asyncio.wait_for(asyncio.gather(approve(a),approve(b),return_exceptions=True),timeout=10)
    assert sum(isinstance(r,dict) for r in results)==1
    assert sum(isinstance(r,(ValueError,DBAPIError)) for r in results)==1
    assert await counts(items)==(2,2,0)

@pytest.mark.asyncio
async def test_worker_never_sees_partial_batch_before_commit(config,monkeypatch):
    items=await batch_setup(monkeypatch);p=await stage(items);entered=asyncio.Event();release=asyncio.Event()
    async def held_approval():
        async with SessionFactory() as s:
            # Pause at transaction commit using a session event plus a separate
            # async checkpoint immediately after final flush, before context exit.
            real_flush=s.flush
            async def flush(*a,**kw):
                await real_flush(*a,**kw)
                if any(isinstance(o,Dispatch) for o in s.sync_session.identity_map.values()) or await s.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.execution_id.in_([UUID(i['execution_id']) for i in items])))==2:
                    entered.set();await release.wait()
            monkeypatch.setattr(s,'flush',flush)
            return await flow.approve(s,UUID(p['id']),snapshot_hash=p['snapshot_hash'],authenticated_owner=True,exact_batch_approved=True,public_posts_approved=True,media_disclosures_approved=True,evidence_ref='trusted-message:synthetic-local-only')
    task=asyncio.create_task(held_approval())
    try:
        await asyncio.wait_for(entered.wait(),10)
        assert await counts(items)==(0,0,0)
    finally:release.set()
    await task
    assert await counts(items)==(2,2,0)

@pytest.mark.asyncio
async def test_staging_key_and_fresh_transaction_contract(config,monkeypatch):
    items=await batch_setup(monkeypatch);key=str(uuid4())
    async with SessionFactory() as s:a=await flow.stage(s,items,request_key=key)
    async with SessionFactory() as s:assert (await flow.stage(s,items,request_key=key))['id']==a['id']
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await flow.stage(s,list(reversed(items)),request_key=key)
    async with SessionFactory() as s:
        await s.execute(select(1))
        with pytest.raises(ValueError,match='fresh transaction'):await flow.stage(s,items,request_key=str(uuid4()))
    with pytest.raises(ValueError,match='Duplicate'):await stage([items[0],items[0]])

@pytest.mark.asyncio
async def test_changed_private_bytes_on_second_item_blocks_all(config,monkeypatch):
    items=await batch_setup(monkeypatch);p=await stage(items)
    from app.application import instagram_media_pin as pin
    real=pin.recheck_pinned_bytes;calls=0
    async def changed(s,job):
        nonlocal calls
        calls+=1
        if calls==2:raise ValueError('Private bytes changed')
        return await real(s,job)
    monkeypatch.setattr(pin,'recheck_pinned_bytes',changed)
    with pytest.raises(ValueError,match='Private bytes'):await approve(p)
    assert calls==2 and await counts(items)==(0,0,0)

@pytest.mark.asyncio
async def test_locked_material_fails_fast_without_partial_rows(config,monkeypatch):
    items=await batch_setup(monkeypatch);p=await stage(items)
    async with SessionFactory() as holder:
        job=await holder.get(Job,UUID(items[-1]['execution_id']))
        await holder.execute(select(Artifact).where(Artifact.id==job.artifact_id).with_for_update())
        with pytest.raises(DBAPIError):await asyncio.wait_for(approve(p),timeout=5)
        assert await counts(items)==(0,0,0)
    assert (await approve(p))['state']=='APPROVED'

@pytest.mark.asyncio
async def test_commit_failure_after_full_flush_rolls_back_entire_batch(config,monkeypatch):
    items=await batch_setup(monkeypatch);p=await stage(items)
    async with SessionFactory() as s:
        def fail(session):raise ValueError('Synthetic commit failure')
        event.listen(s.sync_session,'before_commit',fail)
        with pytest.raises(ValueError,match='commit failure'):
            await flow.approve(s,UUID(p['id']),snapshot_hash=p['snapshot_hash'],authenticated_owner=True,
                exact_batch_approved=True,public_posts_approved=True,media_disclosures_approved=True,evidence_ref='trusted-message:synthetic-local-only')
    assert await counts(items)==(0,0,0)

@pytest.mark.asyncio
@pytest.mark.parametrize('invalid',['mode','missing-choice','duplicate-original','past','too-many'])
async def test_staging_fails_closed_without_saved_partial_plan(config,monkeypatch,invalid):
    items=await batch_setup(monkeypatch)
    async with SessionFactory() as s:
        job=await s.get(Job,UUID(items[-1]['execution_id']))
        if invalid=='mode':job.connection_binding={**job.connection_binding,'login_mode':'INSTAGRAM_LOGIN'}
        if invalid=='missing-choice':await s.delete(await s.get(Selection,job.artifact_id))
        if invalid=='duplicate-original':
            first=await s.get(Job,UUID(items[0]['execution_id']));job.artifact_id=first.artifact_id
        await s.commit()
        before=await s.scalar(select(func.count()).select_from(Batch))
    if invalid=='past':items[-1]['due_at']=oauth.now()-timedelta(seconds=1)
    if invalid=='too-many':items=items*11
    with pytest.raises(ValueError):await stage(items)
    async with SessionFactory() as s:assert await s.scalar(select(func.count()).select_from(Batch))==before


@pytest.mark.asyncio
async def test_tiktok_and_facebook_lock_does_not_block_independent_batch(config,monkeypatch):
    from sqlalchemy import text
    items=await batch_setup(monkeypatch)
    async with SessionFactory() as holder:
        await holder.execute(text('SELECT pg_advisory_xact_lock(606032)'))
        p=await asyncio.wait_for(stage(items),timeout=5)
        assert p['state']=='DRAFT' and await counts(items)==(0,0,0)
