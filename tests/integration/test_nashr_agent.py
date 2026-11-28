"""Owner-only bounded internal task execution with real database rows."""
from uuid import UUID,uuid4
import asyncio
import pytest
from sqlalchemy import select,event,func
from sqlalchemy.orm import Session
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import NashrAgentTaskModel as Task,ArtifactModel as Artifact,PlatformCopyModel as Copy
from app.application import nashr_agent as flow
from tests.integration.test_instagram_execution_core import seed,private_storage
from tests.integration.test_instagram_oauth import config,browser

async def task(action='AUDIT_READINESS'):
    uid,_=await seed()
    async with SessionFactory() as s:
        a=await s.get(Artifact,uid);a.review_status='APPROVED';await s.commit()
        kw=dict(request_text='افحص المادة المختارة',action=action,artifact_ids=[uid])
        p=await flow.preview(s,**kw);t=await flow.create(s,**kw,plan_hash=p['plan_hash'],request_key=str(uuid4()))
    return uid,UUID(t['id'])

@pytest.mark.asyncio
async def test_plan_start_step_durable_result_no_external_calls(monkeypatch):
    import httpx
    def forbidden(*a,**kw):raise AssertionError('No network/model')
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    uid,tid=await task()
    async with SessionFactory() as s:
        await flow.process_one(s,tid)
        assert (await s.get(Task,tid)).cursor==0
    async with SessionFactory() as s:await flow.command(s,tid,'start')
    async with SessionFactory() as s:await flow.process_one(s,tid)
    async with SessionFactory() as s:
        t=await s.get(Task,tid);assert t.state=='COMPLETED' and t.cursor==1 and t.results[0]['targets']
    async with SessionFactory() as s:await flow.process_one(s,tid)
    async with SessionFactory() as s:assert (await s.get(Task,tid)).cursor==1

@pytest.mark.asyncio
async def test_prepare_preserves_existing_copy_and_selection(monkeypatch):
    uid,tid=await task('PREPARE_COPIES')
    async with SessionFactory() as s:
        old=await s.get(Copy,(uid,'instagram'));before=(dict(old.fields),old.version,old.origin)
        await flow.command(s,tid,'start')
    async with SessionFactory() as s:await flow.process_one(s,tid)
    async with SessionFactory() as s:
        old=await s.get(Copy,(uid,'instagram'));assert (old.fields,old.version,old.origin)==before
        assert await s.scalar(select(func.count()).select_from(Copy).where(Copy.artifact_id==uid))==6
        assert (await s.get(Artifact,uid)).review_status=='APPROVED'

@pytest.mark.asyncio
async def test_stop_persists_and_cannot_restart(monkeypatch):
    uid,tid=await task()
    async with SessionFactory() as s:await flow.command(s,tid,'start');await flow.command(s,tid,'stop')
    async with SessionFactory() as s:await flow.process_one(s,tid)
    async with SessionFactory() as s:
        t=await s.get(Task,tid);assert t.state=='STOPPED' and t.cursor==0
        with pytest.raises(ValueError):await flow.command(s,tid,'start')

@pytest.mark.asyncio
async def test_changed_source_blocks_not_silent_replan(monkeypatch):
    uid,tid=await task('PREPARE_COPIES')
    async with SessionFactory() as s:
        a=await s.get(Artifact,uid);a.content='changed';await s.commit();await flow.command(s,tid,'start')
    async with SessionFactory() as s:await flow.process_one(s,tid)
    async with SessionFactory() as s:
        t=await s.get(Task,tid);assert t.state=='COMPLETED_WITH_BLOCKERS' and t.results[0]['state']=='BLOCKED'
        assert await s.scalar(select(func.count()).select_from(Copy).where(Copy.artifact_id==uid))==1

@pytest.mark.asyncio
async def test_rollback_no_partial_copies_or_result(monkeypatch):
    uid,tid=await task('PREPARE_COPIES')
    async with SessionFactory() as s:await flow.command(s,tid,'start')
    def fail(*a):raise ValueError('Synthetic commit failure')
    event.listen(Session,'before_commit',fail)
    try:
        async with SessionFactory() as s:
            with pytest.raises(ValueError):await flow.process_one(s,tid)
    finally:event.remove(Session,'before_commit',fail)
    async with SessionFactory() as s:
        t=await s.get(Task,tid);assert t.cursor==0 and t.results==[]
        assert await s.scalar(select(func.count()).select_from(Copy).where(Copy.artifact_id==uid))==1

@pytest.mark.asyncio
async def test_two_workers_one_step(monkeypatch):
    uid,tid=await task('PREPARE_COPIES')
    async with SessionFactory() as s:await flow.command(s,tid,'start')
    async def one():
        async with SessionFactory() as s:await flow.process_one(s,tid)
    await asyncio.gather(one(),one())
    async with SessionFactory() as s:assert (await s.get(Task,tid)).cursor==1

@pytest.mark.asyncio
async def test_http_owner_origin_immutable_scope_and_idempotence(config,monkeypatch):
    import httpx
    from app.main import app
    uid,_=await seed();payload=dict(request_text='احذف كل شيء وانشر الآن',action='AUDIT_READINESS',artifact_ids=[str(uid)])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.get('/api/agent/tasks')).status_code==401
        assert (await c.post('/api/agent/preview',json=payload)).status_code==401
    async with browser() as c:
        assert (await c.post('/api/agent/preview',json=payload,headers={'Origin':'https://other.invalid'})).status_code==403
        assert (await c.post('/api/agent/preview',json={**payload,'action':'PUBLISH'})).status_code==409
        assert (await c.post('/api/agent/preview',json={**payload,'approved':True})).status_code==422
        r=await c.post('/api/agent/preview',json=payload);assert r.status_code==200
        assert r.json()['plan']['action']=='AUDIT_READINESS' and not r.json()['plan']['publication_authorized']
        create={**payload,'plan_hash':r.json()['plan_hash'],'request_key':str(uuid4())}
        a=await c.post('/api/agent/tasks',json=create);b=await c.post('/api/agent/tasks',json=create)
        assert a.status_code==b.status_code==200 and a.json()==b.json()
        tid=a.json()['id'];assert (await c.post('/api/agent/tasks/'+tid+'/start')).json()['state']=='RUNNING'
        assert (await c.post('/api/agent/tasks/'+tid+'/stop')).json()['state']=='STOPPED'
        assert (await c.get('/api/agent/tasks')).headers['cache-control']=='no-store'

@pytest.mark.asyncio
async def test_concurrent_create_is_one_plan(monkeypatch):
    uid,_=await seed()
    kw=dict(request_text='فحص فقط',action='AUDIT_READINESS',artifact_ids=[uid])
    async with SessionFactory() as s:p=await flow.preview(s,**kw)
    key=str(uuid4())
    async def create():
        async with SessionFactory() as s:return await flow.create(s,**kw,plan_hash=p['plan_hash'],request_key=key)
    a,b=await asyncio.gather(create(),create());assert a['id']==b['id']

@pytest.mark.asyncio
async def test_stop_between_steps_keeps_completed_result(monkeypatch):
    uid,_=await seed();uid2,_=await seed()
    async with SessionFactory() as s:
        kw=dict(request_text='فحص مادتين',action='AUDIT_READINESS',artifact_ids=[uid,uid2]);p=await flow.preview(s,**kw)
        t=await flow.create(s,**kw,plan_hash=p['plan_hash'],request_key=str(uuid4()));tid=UUID(t['id']);await flow.command(s,tid,'start')
    async with SessionFactory() as s:await flow.process_one(s,tid)
    async with SessionFactory() as s:await flow.command(s,tid,'stop')
    async with SessionFactory() as s:await flow.process_one(s,tid)
    async with SessionFactory() as s:
        t=await s.get(Task,tid);assert t.state=='STOPPED' and t.cursor==1 and len(t.results)==1

@pytest.mark.asyncio
async def test_task_body_is_context_not_executable_code(monkeypatch):
    uid,tid=await task()
    async with SessionFactory() as s:
        t=await s.get(Task,tid);t.plan={**t.plan,'action':'PUBLISH'};await s.commit();await flow.command(s,tid,'start')
    async with SessionFactory() as s:
        with pytest.raises(ValueError,match='integrity'):await flow.process_one(s,tid)
