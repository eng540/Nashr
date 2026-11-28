"""Synthetic local DB only. Private reviews never enqueue or contact Meta."""
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func,event
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import (InstagramPrivateBatchReviewModel as Batch,
    InstagramExecutionModel as Job,InstagramDispatchModel as Dispatch,InstagramPublishDecisionModel as Decision,
    InstagramMediaGrantModel as Grant,ArtifactModel as Artifact,PlatformCopyModel as Copy,
    DistributionSelectionModel as Selection,InstagramConnectionModel as Connection,PlatformMediaInspectionModel as Inspection)
from app.application import instagram_batch_review as flow,instagram_oauth as oauth
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_instagram_unified_execution_drafts import connected
from tests.integration.test_instagram_execution_core import seed,private_storage
from tests.integration.test_instagram_oauth import config,browser

async def setup(monkeypatch,n=2):
    await connected(monkeypatch);items=[]
    for _ in range(n):
        uid,jid=await seed()
        async with SessionFactory() as s:
            (await s.get(Job,jid)).state='CANCELLED'
            a=await s.get(Artifact,uid)
            s.add(Selection(artifact_id=uid,platforms=['instagram','facebook'],source_fingerprint=source_fingerprint(a),saved_at=oauth.now()));await s.commit()
        items.append(dict(artifact_id=str(uid),due_at=oauth.now()+timedelta(hours=1),timezone='Asia/Riyadh',share_to_feed=None))
    return items

async def preview(items):
    async with SessionFactory() as s:return await flow.preview(s,items)

async def save(items,p,key=None):
    async with SessionFactory() as s:return await flow.save(s,items,preview_hash=p['preview_hash'],request_key=key or str(uuid4()))

async def counts():
    async with SessionFactory() as s:return [await s.scalar(select(func.count()).select_from(m)) for m in [Job,Decision,Dispatch,Grant,Batch]]

@pytest.mark.asyncio
async def test_private_order_exact_words_idempotency_history_cancel_zero_execution(config,monkeypatch):
    items=await setup(monkeypatch);before=await counts()
    import httpx
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    def forbidden(*a,**k):raise AssertionError('No provider or media bytes')
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden);monkeypatch.setattr(S3ArtifactStorage,'from_environment',forbidden)
    p=await preview(items);assert p['blocked_count']==0 and p['can_save_draft']
    assert [i['artifact_id'] for i in p['items']]==[i['artifact_id'] for i in items]
    assert all(i['caption']=='تعليق صناعي فقط' and i['selected_platforms']==['instagram','facebook'] for i in p['items'])
    assert 'private-token' not in str(p) and not p['scheduled'] and not p['execution_enabled']
    key=str(uuid4());d=await save(items,p,key);again=await save(items,p,key);assert d['id']==again['id']
    after=await counts();assert after[:4]==before[:4] and after[4]==before[4]+1
    async with SessionFactory() as s:
        history=await flow.history(s);assert history['items'][0]['id']==d['id'] and history['items'][0]['stale'] is None
        assert not (await flow.get_review(s,UUID(d['id'])))['stale']
        canceled=await flow.cancel(s,UUID(d['id']));assert canceled['state']=='CANCELLED' and not canceled['remote_changed']
    assert (await save(items,p,key))['state']=='CANCELLED'
    with pytest.raises(ValueError):await save(list(reversed(items)),p,key)

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['copy','original','selection','selection-version','account','reconnect','token','inspection','new-job'])
async def test_whole_snapshot_rejects_changed_later_entry(config,monkeypatch,change):
    items=await setup(monkeypatch);p=await preview(items);before=await counts();uid=UUID(items[-1]['artifact_id'])
    async with SessionFactory() as s:
        if change=='copy':(await s.get(Copy,(uid,'instagram'))).version+=1
        if change=='original':(await s.get(Artifact,uid)).review_status='DRAFT'
        if change=='selection':(await s.get(Selection,uid)).platforms=['facebook']
        if change=='selection-version':(await s.get(Selection,uid)).saved_at+=timedelta(seconds=1)
        conn=await s.get(Connection,1)
        if change=='account':conn.username='changed'
        if change=='reconnect':conn.connected_at+=timedelta(seconds=1)
        if change=='token':conn.token_ciphertext='changed-private-token'
        if change=='inspection':
            r=await s.scalar(select(Inspection).where(Inspection.artifact_id==uid,Inspection.platform=='instagram'));r.selected=False
        if change=='new-job':
            j=await s.scalar(select(Job).where(Job.artifact_id==uid));j.state='CREATE_UNKNOWN'
        await s.commit()
    with pytest.raises(ValueError):await save(items,p)
    assert (await counts())[4]==before[4]

@pytest.mark.asyncio
async def test_excluded_stale_conflict_account_history_and_blocked_private_save(config,monkeypatch):
    items=await setup(monkeypatch);uid=UUID(items[1]['artifact_id'])
    async with SessionFactory() as s:
        (await s.get(Selection,uid)).platforms=['facebook']
        j=await s.scalar(select(Job).where(Job.artifact_id==uid));j.state='PUBLISH_UNKNOWN';await s.commit()
    p=await preview(items);assert p['blocked_count']==1
    assert 'Instagram' in str(p['items'][1]['blockers']) and len(p['items'][1]['blockers'])>=2
    assert p['items'][1]['history'][0]['state']=='PUBLISH_UNKNOWN'
    d=await save(items,p);assert not d['scheduled'] and d['snapshot']['blocked_count']==1

@pytest.mark.asyncio
async def test_storage_insert_failure_rolls_back_no_other_objects(config,monkeypatch):
    items=await setup(monkeypatch);p=await preview(items);before=await counts()
    def fail(*a):raise ValueError('synthetic storage failure')
    event.listen(Batch,'before_insert',fail)
    try:
        with pytest.raises(ValueError):await save(items,p)
    finally:event.remove(Batch,'before_insert',fail)
    assert await counts()==before

@pytest.mark.asyncio
async def test_owner_origin_strict_inputs_no_activation_route(config,monkeypatch):
    import httpx
    from app.main import app
    items=await setup(monkeypatch);body={'items':[{**i,'due_at':i['due_at'].isoformat()} for i in items]};base='/api/connections/instagram/batch-reviews'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as anon:
        assert (await anon.get(base)).status_code==401
        assert (await anon.post(base+'/preview',json=body)).status_code==401
    async with browser() as c:
        assert (await c.post(base+'/preview',headers={'Origin':'https://other.invalid'},json=body)).status_code==403
        assert (await c.post(base+'/preview',json={**body,'authorized':True})).status_code==422
        p=await c.post(base+'/preview',json=body);assert p.status_code==200,p.text
        assert p.headers['cache-control']=='no-store'
        d=await c.post(base,json={**body,'preview_hash':p.json()['preview_hash'],'request_key':str(uuid4())});assert d.status_code==200,d.text
        assert (await c.get(base)).json()['items']
        assert (await c.post(base+'/'+d.json()['id']+'/approve',json={})).status_code==404
        assert (await c.post(base+'/'+d.json()['id']+'/cancel')).json()['state']=='CANCELLED'
        dup={**body,'items':[body['items'][0],body['items'][0]]};assert (await c.post(base+'/preview',json=dup)).status_code==409
        wrong={**body,'items':[{**body['items'][0],'share_to_feed':'false'}]};assert (await c.post(base+'/preview',json=wrong)).status_code==422

@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['past','distant','naive','zone','empty','duplicate','feed','oversize'])
async def test_invalid_exact_inputs_cannot_save(config,monkeypatch,bad):
    items=await setup(monkeypatch,1)
    if bad=='past':items[0]['due_at']=oauth.now()-timedelta(seconds=1)
    if bad=='distant':items[0]['due_at']=oauth.now()+timedelta(days=8)
    if bad=='naive':items[0]['due_at']=items[0]['due_at'].replace(tzinfo=None)
    if bad=='zone':items[0]['timezone']='not/a-zone'
    if bad=='empty':items=[]
    if bad=='duplicate':items=items*2
    if bad=='feed':items[0]['share_to_feed']='false'
    if bad=='oversize':items=items*21
    before=await counts()
    with pytest.raises(ValueError):await preview(items)
    assert await counts()==before

@pytest.mark.asyncio
async def test_elapsed_or_changed_saved_history_is_marked_stale_without_rewriting(config,monkeypatch):
    items=await setup(monkeypatch,1);p=await preview(items);saved=await save(items,p)
    async with SessionFactory() as s:
        copy=await s.get(Copy,(UUID(items[0]['artifact_id']),'instagram'));copy.fields={**copy.fields,'description':'new saved copy'};await s.commit()
        row=await flow.get_review(s,UUID(saved['id']))
        assert row['stale'] and row['snapshot']['items'][0]['caption']=='تعليق صناعي فقط'

@pytest.mark.asyncio
async def test_conflict_beyond_display_limit_is_not_hidden(config,monkeypatch):
    items=await setup(monkeypatch,1);uid=UUID(items[0]['artifact_id'])
    # A published legacy same-account operation blocks even without a Unified dispatch.
    async with SessionFactory() as s:
        row=await s.scalar(select(Job).where(Job.artifact_id==uid));row.state='PUBLISHED';await s.commit()
    p=await preview(items);assert p['blocked_count']==1

@pytest.mark.asyncio
async def test_preview_hash_and_key_cannot_be_reused_for_another_snapshot(config,monkeypatch):
    items=await setup(monkeypatch,1);p=await preview(items);key=str(uuid4());original=await save(items,p,key)
    async with SessionFactory() as s:
        copy=await s.get(Copy,(UUID(items[0]['artifact_id']),'instagram'));copy.version+=1;await s.commit()
    # A lost-reply retry retrieves immutable historical receipt, not new consent.
    again=await save(items,p,key);assert again['id']==original['id']
    updated=await preview(items)
    with pytest.raises(ValueError):await save(items,updated,key)

@pytest.mark.asyncio
async def test_parallel_private_saves_do_not_duplicate_or_create_execution(config,monkeypatch):
    import asyncio
    items=await setup(monkeypatch,1);p=await preview(items);key=str(uuid4());before=await counts()
    result=await asyncio.gather(save(items,p,key),save(items,p,key),return_exceptions=True)
    good=[r for r in result if isinstance(r,dict)]
    assert good
    after=await counts();assert after[:4]==before[:4] and after[4]==before[4]+1
    again=await save(items,p,key);assert again['id']==good[0]['id']
