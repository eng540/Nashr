"""Private provenance only, synthetic DB and no external access."""
from copy import deepcopy
from uuid import UUID, uuid4
import asyncio
import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import (
    InstagramPrivateBatchPreparationModel as Preparation,
    InstagramPrivateBatchReviewModel as Batch,
    InstagramPlanDraftModel as Review, InstagramExecutionModel as Job)
from app.application import instagram_private_child_resolver as flow
from tests.integration.test_instagram_batch_preparation import saved, prepare, counts
from tests.integration.test_instagram_oauth import config
from tests.integration.test_instagram_execution_core import private_storage

async def setup(monkeypatch):
    _, _, d = await saved(monkeypatch)
    return d, await prepare(d)

async def resolve(d, r, **kw):
    args = dict(review_id=UUID(d['id']), snapshot_hash=d['snapshot_hash'])
    args.update(kw)
    async with SessionFactory() as s:
        return await flow.resolve(s, UUID(r['id']), **args)

@pytest.mark.asyncio
async def test_exact_private_order_repeat_no_effects(config, monkeypatch):
    d, r = await setup(monkeypatch)
    before = await counts()
    import httpx
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    def forbidden(*a, **kw): raise AssertionError('No provider or bytes')
    monkeypatch.setattr(httpx.AsyncClient, 'request', forbidden)
    monkeypatch.setattr(S3ArtifactStorage, 'from_environment', forbidden)
    out = await resolve(d, r)
    assert out == await resolve(d, r)
    assert out['items'] == r['items']
    assert not out['execution_enabled'] and not out['stop_enabled'] and not out['currentness_verified']
    assert 'token_hash' not in str(out) and 'connection_binding' not in str(out)
    assert before == await counts()

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['job-caption','job-artifact','job-state','job-container','job-media',
    'job-mode','job-parent','job-review','job-hash','job-account','job-inspection','job-feed',
    'draft-caption','draft-hash','draft-cancel','parent-cancel','parent-hash','parent-words',
    'receipt-time','receipt-order','receipt-duplicate','receipt-missing','receipt-extra','foreign-child',
    'binding-config','binding-token','binding-connected','binding-business','binding-malformed'])
async def test_changed_or_foreign_later_child_fail_closed(config, monkeypatch, change):
    d, r = await setup(monkeypatch)
    foreign = None
    if change == 'foreign-child':
        _, foreign = await setup(monkeypatch)
    async with SessionFactory() as s:
        receipt = await s.get(Preparation, UUID(r['id']))
        parent = await s.get(Batch, UUID(d['id']))
        entry = r['items'][-1]
        job = await s.get(Job, UUID(entry['execution_id']))
        draft = await s.get(Review, UUID(entry['review_id']))
        fields = {'job-caption':('caption','changed'), 'job-artifact':('artifact_id',UUID(r['items'][0]['artifact_id'])),
            'job-state':('state','CREATE_UNKNOWN'), 'job-container':('container_id','known'),
            'job-media':('media_id','published'), 'job-account':('account_id','foreign'),
            'job-inspection':('inspection_id',None), 'job-feed':('share_to_feed',True)}
        if change in fields: setattr(job,*fields[change])
        for name,key,value in [('job-mode','login_mode','UNIFIED'),('job-parent','private_batch_preparation_id',str(uuid4())),
            ('job-review','review_id',str(uuid4())),('job-hash','review_hash','f'*64)]:
            if change == name: job.connection_binding = {**job.connection_binding,key:value}
        if change.startswith('binding-'):
            binding = dict(job.connection_binding)
            key = {'binding-config':'config_hash','binding-token':'token_hash',
                'binding-connected':'connected_at','binding-business':'client_business_id',
                'binding-malformed':'connected_at'}[change]
            if change == 'binding-malformed': binding.pop(key)
            elif change == 'binding-connected': binding[key] = '2020-01-01T00:00:00+00:00'
            else: binding[key] = 'changed'
            job.connection_binding = binding
        if change == 'draft-caption':
            draft.snapshot = {**draft.snapshot,'caption':'changed'}
        if change == 'draft-hash': draft.snapshot_hash = 'f'*64
        if change == 'draft-cancel': draft.state = 'CANCELLED'
        if change == 'parent-cancel': parent.state = 'CANCELLED'
        if change == 'parent-hash': parent.snapshot_hash = 'f'*64
        if change == 'parent-words':
            value = deepcopy(parent.snapshot); value['items'][-1]['caption'] = 'changed'; parent.snapshot = value
        value = deepcopy(receipt.items)
        if change == 'receipt-time': value[-1]['due_at'] = value[0]['due_at']
        if change == 'receipt-order': value.reverse()
        if change == 'receipt-duplicate': value[-1] = value[0]
        if change == 'receipt-missing': value.pop()
        if change == 'receipt-extra': value.append(value[0])
        if change == 'foreign-child': value[-1] = foreign['items'][-1]
        receipt.items = value
        await s.commit()
    before = await counts()
    with pytest.raises(ValueError): await resolve(d,r)
    assert before == await counts()

@pytest.mark.asyncio
async def test_parent_arguments_and_fresh_transaction_required(config,monkeypatch):
    d,r = await setup(monkeypatch)
    for kw in (dict(review_id=uuid4()),dict(snapshot_hash='e'*64)):
        with pytest.raises(ValueError): await resolve(d,r,**kw)
    async with SessionFactory() as s:
        await s.execute(select(Job.id).limit(1))
        with pytest.raises(ValueError):
            await flow.resolve(s,UUID(r['id']),review_id=UUID(d['id']),snapshot_hash=d['snapshot_hash'])

@pytest.mark.asyncio
async def test_later_child_lock_conflict_leaves_no_mutation(config,monkeypatch):
    d,r = await setup(monkeypatch);before = await counts()
    async with SessionFactory() as other:
        await other.execute(select(Job).where(Job.id==UUID(r['items'][-1]['execution_id'])).with_for_update())
        with pytest.raises(DBAPIError): await resolve(d,r)
        assert before == await counts()
    assert (await resolve(d,r))['items']==r['items']

@pytest.mark.asyncio
async def test_unreceipted_extra_owned_job_is_rejected(config,monkeypatch):
    d,r = await setup(monkeypatch)
    async with SessionFactory() as s:
        original = await s.get(Job,UUID(r['items'][-1]['execution_id']))
        values = {c.name:getattr(original,c.name) for c in Job.__table__.columns if c.name!='id'}
        s.add(Job(**values));await s.commit()
    before = await counts()
    with pytest.raises(ValueError): await resolve(d,r)
    assert before == await counts()

@pytest.mark.asyncio
async def test_malformed_receipt_rejected_as_domain_error(config,monkeypatch):
    d,r = await setup(monkeypatch)
    async with SessionFactory() as s:
        receipt=await s.get(Preparation,UUID(r['id']));receipt.items=[{'artifact_id':None}];await s.commit()
    with pytest.raises(ValueError): await resolve(d,r)
