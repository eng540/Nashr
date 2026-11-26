from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
import httpx
import pytest
from sqlalchemy import select, func
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import (ArtifactModel, InstagramExecutionModel as IG,
    InstagramPublishDecisionModel as Decision, InstagramDispatchModel as Dispatch,
    FacebookReelJobModel as FB, FacebookExecutionModel as FT, PublicationModel)
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['instagram', 'facebook', 'facebook_text', 'facebook_photo'])
async def test_queue_projects_pending_meta_schedule_without_creating_or_sending(platform):
    token = 'meta-plan-' + uuid4().hex
    uid = await _seed_text_artifact(token)
    now = datetime.now(timezone.utc)
    due = now + timedelta(hours=1)
    async with SessionFactory() as s:
        a = await s.get(ArtifactModel, UUID(uid)); a.review_status = 'APPROVED'
        if platform == 'instagram':
            job = IG(artifact_id=a.id, account_id='123', connection_binding={'login_mode':'UNIFIED'}, source_fingerprint='a'*64, copy_version=1, media_sha256='b'*64, kind='VIDEO', caption=token, alt_text='', state='DRAFT', created_at=now, updated_at=now)
            s.add(job); await s.flush()
            decision = Decision(execution_id=job.id, snapshot_hash='c'*64, snapshot={'due_at':due.isoformat(),'timezone':'Asia/Riyadh'}, evidence_ref='trusted-message:meta_queue_test_123', state='APPROVED', created_at=now, expires_at=due+timedelta(minutes=15))
            s.add(decision); await s.flush()
            dispatch = Dispatch(execution_id=job.id, decision_id=decision.id, due_at=due, state='PENDING', updated_at=now)
            s.add(dispatch)
        elif platform == 'facebook':
            job = FB(artifact_id=a.id, snapshot={'due_at':due.isoformat(),'timezone':'Asia/Riyadh','caption':token,'connection':{'page_id':'789'}}, snapshot_hash='d'*64, state='APPROVED', evidence_ref='owner-session:meta_queue_test_456', approved_until=due+timedelta(minutes=30), created_at=now, updated_at=now)
            s.add(job)
        else:
            job = FT(artifact_id=a.id,page_id='789',source_fingerprint='a'*64,copy_version=1,kind='IMAGE' if platform=='facebook_photo' else 'TEXT',message=token,total_bytes=0,runtime_snapshot={'timezone':'Asia/Riyadh'},runtime_hash='d'*64,evidence_ref='owner-session:meta_queue_test_789',due_at=due,approved_until=due+timedelta(minutes=30),state='APPROVED',created_at=now,updated_at=now)
            s.add(job)
        await s.commit(); jid = job.id
        before = (await s.execute(select(func.count()).select_from(PublicationModel))).scalar_one()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        async def row():
            r = await c.get('/api/publishing-queue',params={'q':token}); assert r.status_code == 200, r.text
            return r.json()['items'][0]
        item = await row()
        assert item['state'] == 'PLANNED'
        assert item['execution_ready'] is False
        assert item['pending_operations'] == [{'id':str(jid),'platform':platform,'due_at':due.isoformat()}]
        assert 'meta_queue_test' not in str(item)
        assert (await c.get('/api/publishing-queue',params={'q':token,'state':'PLANNED'})).json()['total'] == 1
        async with SessionFactory() as s:
            if platform == 'instagram':
                d = await s.get(Decision,decision.id); d.state='REVOKED'
            else:
                j = await s.get(FB if platform=='facebook' else FT,jid); j.approved_until=now-timedelta(minutes=1)
            await s.commit()
        assert (await row())['state'] != 'PLANNED'
        assert (await row())['pending_operations'] == []
    async with SessionFactory() as s:
        assert (await s.execute(select(func.count()).select_from(PublicationModel))).scalar_one() == before
        if platform=='instagram': assert (await s.get(Dispatch,dispatch.id)).state == 'PENDING'


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['revoked','expired','cancelled','claimed','published','synthetic','wrong_decision','wrong_mode'])
async def test_queue_ignores_nonpending_or_unbound_instagram_schedule(condition):
    token='meta-negative-'+uuid4().hex
    uid=await _seed_text_artifact(token); now=datetime.now(timezone.utc); due=now+timedelta(hours=1)
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid)); a.review_status='APPROVED'
        job=IG(artifact_id=a.id,account_id='123',connection_binding={'login_mode':'DIRECT' if condition=='wrong_mode' else 'UNIFIED'},source_fingerprint='a'*64,copy_version=1,media_sha256='b'*64,kind='VIDEO',caption=token,alt_text='',state='PUBLISHED' if condition=='published' else 'DRAFT',created_at=now,updated_at=now)
        s.add(job); await s.flush()
        if condition=='wrong_decision':
            other=IG(artifact_id=a.id,account_id='123',connection_binding={'login_mode':'UNIFIED'},source_fingerprint='a'*64,copy_version=1,media_sha256='b'*64,kind='VIDEO',caption=token,alt_text='',state='DRAFT',created_at=now,updated_at=now)
            s.add(other); await s.flush()
        d=Decision(execution_id=other.id if condition=='wrong_decision' else job.id,snapshot_hash='c'*64,snapshot={},evidence_ref='synthetic:test' if condition=='synthetic' else 'trusted-message:negative_case_123',state='REVOKED' if condition=='revoked' else 'APPROVED',created_at=now,expires_at=now-timedelta(minutes=1) if condition=='expired' else due+timedelta(minutes=15))
        s.add(d); await s.flush()
        s.add(Dispatch(execution_id=job.id,decision_id=d.id,due_at=due,state='CANCELLED' if condition=='cancelled' else 'CLAIMED' if condition=='claimed' else 'PENDING',updated_at=now)); await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        result=(await c.get('/api/publishing-queue',params={'q':token})).json()
        assert result['items'][0]['pending_operations']==[]
        assert result['items'][0]['state']!='PLANNED'


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['facebook','facebook_text'])
@pytest.mark.parametrize('condition', ['draft','cancelled','synthetic','no_schedule','no_runtime'])
async def test_queue_excludes_meta_preparation_and_non_schedules(platform, condition):
    token='meta-fb-negative-'+uuid4().hex
    uid=await _seed_text_artifact(token); now=datetime.now(timezone.utc); due=now+timedelta(hours=1)
    evidence='synthetic:test' if condition=='synthetic' else 'owner-session:negative_fb_123'
    state={'draft':'DRAFT','cancelled':'CANCELLED'}.get(condition,'APPROVED')
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid)); a.review_status='APPROVED'
        if platform=='facebook':
            j=FB(artifact_id=a.id,snapshot={} if condition in {'no_schedule','no_runtime'} else {'due_at':due.isoformat()},snapshot_hash='d'*64,state=state,evidence_ref=evidence,approved_until=due+timedelta(minutes=30),created_at=now,updated_at=now)
        else:
            j=FT(artifact_id=a.id,page_id='789',source_fingerprint='a'*64,copy_version=1,kind='TEXT',message=token,total_bytes=0,runtime_snapshot=None if condition=='no_runtime' else {},evidence_ref=evidence,due_at=None if condition=='no_schedule' else due,approved_until=due+timedelta(minutes=30),state=state,created_at=now,updated_at=now)
        s.add(j); await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        row=(await c.get('/api/publishing-queue',params={'q':token})).json()['items'][0]
        assert row['pending_operations']==[]
        assert row['state']!='PLANNED'


@pytest.mark.asyncio
async def test_saved_meta_schedule_keeps_failure_attention_and_prior_publication_visible():
    token='meta-priority-'+uuid4().hex
    uid=await _seed_text_artifact(token); now=datetime.now(timezone.utc); due=now+timedelta(hours=1)
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid)); a.review_status='APPROVED'
        pending=FB(artifact_id=a.id,snapshot={'due_at':due.isoformat()},snapshot_hash='d'*64,state='APPROVED',evidence_ref='owner-session:priority_test_123',approved_until=due+timedelta(minutes=30),created_at=now,updated_at=now)
        s.add(pending)
        s.add(PublicationModel(knowledge_unit_id=a.source_knowledge_unit_id,artifact_id=a.id,platform='telegram',destination='failed-target',content=token,status='FAILED',created_at=now))
        s.add(PublicationModel(knowledge_unit_id=a.source_knowledge_unit_id,artifact_id=a.id,platform='telegram',destination='published-target',content=token,status='PUBLISHED',external_id='prior-confirmed',created_at=now))
        await s.commit(); jid=pending.id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        row=(await c.get('/api/publishing-queue',params={'q':token})).json()['items'][0]
        assert row['state']=='ATTENTION'
        assert row['pending_operations']==[{'id':str(jid),'platform':'facebook','due_at':due.isoformat()}]
        assert next(x for x in row['publication_outcomes'] if x['platform']=='telegram')=={'platform':'telegram','attempts':2,'confirmed_targets':1,'unresolved_failures':1}
