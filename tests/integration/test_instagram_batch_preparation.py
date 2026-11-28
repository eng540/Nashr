"""Dormant atomic private preparation, synthetic DB, no external effects."""
from uuid import UUID,uuid4
import asyncio
import pytest
from sqlalchemy import select,func,event
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import (InstagramPrivateBatchPreparationModel as Preparation,
    InstagramPrivateBatchReviewModel as BatchReview,InstagramPlanDraftModel as Review,InstagramExecutionModel as Job,
    InstagramDispatchModel as Dispatch,InstagramPublishDecisionModel as Decision,InstagramMediaGrantModel as Grant,
    PlatformCopyModel as Copy)
from app.application import instagram_batch_preparation as flow
from tests.integration.test_instagram_batch_review import setup,preview,save
from tests.integration.test_instagram_execution_core import private_storage
from tests.integration.test_instagram_oauth import config,browser

async def saved(monkeypatch):
    items=await setup(monkeypatch);p=await preview(items);d=await save(items,p);return items,p,d

async def prepare(d,key=None):
    async with SessionFactory() as s:return await flow.prepare(s,UUID(d['id']),snapshot_hash=d['snapshot_hash'],request_key=key or str(uuid4()))

async def counts():
    async with SessionFactory() as s:return [await s.scalar(select(func.count()).select_from(m)) for m in [Preparation,Review,Job,Decision,Dispatch,Grant]]

@pytest.mark.asyncio
async def test_atomic_private_receipt_owned_ids_idempotency_no_provider_or_bytes(config,monkeypatch):
    items,p,d=await saved(monkeypatch);before=await counts()
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    import httpx
    def forbidden(*a,**kw):raise AssertionError('No provider or byte access')
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',forbidden);monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    key=str(uuid4());r=await prepare(d,key);again=await prepare(d,key);assert r==again
    assert [i['artifact_id'] for i in r['items']]==[i['artifact_id'] for i in items]
    after=await counts();assert after==[before[0]+1,before[1]+2,before[2]+2,*before[3:]]
    async with SessionFactory() as s:
        for i in r['items']:
            job=await s.get(Job,UUID(i['execution_id']));review=await s.get(Review,UUID(i['review_id']))
            assert job.state=='DRAFT' and review.state=='DRAFT'
            assert job.caption==p['items'][0]['caption']
            assert job.connection_binding['private_batch_preparation_id']==r['id']
            assert job.connection_binding['login_mode']=='PRIVATE_BATCH_UNIFIED'
    with pytest.raises(ValueError):await prepare(d)

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['copy','cancel','hash'])
async def test_later_entry_stale_or_cancelled_review_creates_no_children(config,monkeypatch,change):
    items,p,d=await saved(monkeypatch);before=await counts()
    async with SessionFactory() as s:
        if change=='copy':(await s.get(Copy,(UUID(items[-1]['artifact_id']),'instagram'))).version+=1
        if change=='cancel':(await s.get(BatchReview,UUID(d['id']))).state='CANCELLED'
        await s.commit()
    if change=='hash':d['snapshot_hash']='f'*64
    with pytest.raises(ValueError):await prepare(d)
    assert await counts()==before

@pytest.mark.asyncio
async def test_second_child_insert_failure_rolls_back_receipt_and_all_children(config,monkeypatch):
    items,p,d=await saved(monkeypatch);before=await counts();calls=0
    def fail(*a):
        nonlocal calls
        calls+=1
        if calls==2:raise ValueError('Second child failure')
    event.listen(Job,'before_insert',fail)
    try:
        with pytest.raises(ValueError):await prepare(d)
    finally:event.remove(Job,'before_insert',fail)
    assert await counts()==before

@pytest.mark.asyncio
async def test_second_connection_cannot_see_partial_children_before_commit(config,monkeypatch):
    items,p,d=await saved(monkeypatch);before=await counts();entered=asyncio.Event();release=asyncio.Event()
    from sqlalchemy.ext.asyncio import AsyncSession
    original=AsyncSession.flush;calls=0
    async def pause(self,*a,**kw):
        nonlocal calls
        value=await original(self,*a,**kw);calls+=1
        if calls==3:entered.set();await release.wait()
        return value
    monkeypatch.setattr(AsyncSession,'flush',pause)
    task=asyncio.create_task(prepare(d));await asyncio.wait_for(entered.wait(),5)
    assert await counts()==before
    release.set();r=await task;assert len(r['items'])==2
    after=await counts();assert after[0]==before[0]+1 and after[2]==before[2]+2 and after[3:]==before[3:]

@pytest.mark.asyncio
async def test_prepared_child_cannot_enter_individual_approval_api(config,monkeypatch):
    items,p,d=await saved(monkeypatch);r=await prepare(d);i=r['items'][0]
    async with browser() as c:
        path=f"/api/connections/instagram/materials/{i['artifact_id']}/execution-drafts/{i['execution_id']}"
        response=await c.post(path+'/proposal',json={'due_at':i['due_at'],'timezone_name':i['timezone']})
        assert response.status_code==404
    from app.application import instagram_batch_decisions as atomic
    from datetime import datetime
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await atomic.stage(s,[dict(execution_id=i['execution_id'],due_at=datetime.fromisoformat(i['due_at']),timezone=i['timezone'])],request_key=str(uuid4()))

@pytest.mark.asyncio
async def test_competing_preparation_key_produces_one_receipt_only(config,monkeypatch):
    items,p,d=await saved(monkeypatch);before=await counts()
    results=await asyncio.gather(prepare(d),prepare(d),return_exceptions=True)
    assert sum(isinstance(r,dict) for r in results)==1
    after=await counts();assert after[0]==before[0]+1 and after[2]==before[2]+2 and after[3:]==before[3:]

@pytest.mark.asyncio
async def test_copy_editor_row_lock_fails_closed_without_partial_insert(config,monkeypatch):
    from sqlalchemy.exc import DBAPIError
    items,p,d=await saved(monkeypatch);before=await counts()
    async with SessionFactory() as editor:
        await editor.execute(select(Copy).where(Copy.artifact_id==UUID(items[-1]['artifact_id']),Copy.platform=='instagram').with_for_update())
        with pytest.raises(DBAPIError):await prepare(d)
        assert await counts()==before
        await editor.rollback()
    assert len((await prepare(d))['items'])==2

@pytest.mark.asyncio
async def test_review_cancellation_serializes_before_preparation(config,monkeypatch):
    from sqlalchemy.exc import DBAPIError
    items,p,d=await saved(monkeypatch);before=await counts()
    async with SessionFactory() as canceler:
        row=await canceler.scalar(select(BatchReview).where(BatchReview.id==UUID(d['id'])).with_for_update())
        row.state='CANCELLED'
        with pytest.raises(DBAPIError):await prepare(d)
        await canceler.commit()
    with pytest.raises(ValueError):await prepare(d)
    assert await counts()==before

@pytest.mark.asyncio
async def test_commit_failure_rolls_back_all_private_rows(config,monkeypatch):
    from sqlalchemy.orm import Session
    items,p,d=await saved(monkeypatch);before=await counts()
    def fail(session):raise ValueError('Synthetic commit failure')
    event.listen(Session,'before_commit',fail)
    try:
        with pytest.raises(ValueError):await prepare(d)
    finally:event.remove(Session,'before_commit',fail)
    assert await counts()==before
