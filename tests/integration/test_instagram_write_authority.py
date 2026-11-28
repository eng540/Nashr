"""Unregistered guard against real synthetic authoritative rows, no providers."""
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import (
    InstagramDispatchModel as Dispatch, InstagramExecutionModel as Job,
    InstagramPublishDecisionModel as Decision, InstagramMediaGrantModel as Grant,
    ArtifactModel as Artifact, PlatformCopyModel as Copy,
    DistributionSelectionModel as Selection, InstagramConnectionModel as Connection)
from app.application import instagram_write_authority as flow
from app.application import instagram_publish_decisions as decisions,instagram_dispatch as dispatch,instagram_media_grants as grants
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_instagram_unified_execution_gates import approved
from tests.integration.test_instagram_execution_core import private_storage
from tests.integration.test_instagram_oauth import config

async def setup(monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        job=await s.get(Job,jid);a=await s.get(Artifact,job.artifact_id)
        if not await s.get(Selection,a.id):s.add(Selection(artifact_id=a.id,platforms=['instagram'],source_fingerprint=source_fingerprint(a),saved_at=decisions.now()))
        await s.commit();d=await dispatch.schedule(s,jid,did)
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
        g,_=await grants.mint(s,jid,did)
        return jid,d.id,did,g.id,due

async def validate(ids,step='CREATE_CONTAINER'):
    async with SessionFactory() as s:
        async with s.begin():
            return await flow.validate_locked(s,ids[1],step=step,grant_id=ids[3])

@pytest.mark.asyncio
async def test_real_authoritative_rows_both_steps_no_commit_or_provider(config,monkeypatch):
    ids=await setup(monkeypatch)
    import httpx
    def forbidden(*a,**kw):raise AssertionError('No provider')
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    rows=await validate(ids);assert rows[1].id==ids[0]
    async with SessionFactory() as s:
        job=await s.get(Job,ids[0]);job.state='WAITING_MEDIA';job.container_id='200'
        (await s.get(Dispatch,ids[1])).state='WAITING_MEDIA';await s.commit()
    assert (await validate(ids,'PUBLISH'))[1].container_id=='200'
    async with SessionFactory() as s:
        assert (await s.get(Job,ids[0])).state=='WAITING_MEDIA'
        assert (await s.get(Decision,ids[2])).state=='APPROVED'

@pytest.mark.asyncio
@pytest.mark.parametrize('step',['CREATE_CONTAINER','PUBLISH'])
@pytest.mark.parametrize('change',['revoked','expired','grant-revoked','grant-expired','grant-foreign',
    'grant-hash','grant-too-long','connection','copy','selection','source','evidence','snapshot','private-batch','unknown'])
async def test_each_write_rechecks_real_records(config,monkeypatch,step,change):
    ids=await setup(monkeypatch)
    async with SessionFactory() as s:
        job=await s.get(Job,ids[0]);d=await s.get(Dispatch,ids[1]);decision=await s.get(Decision,ids[2]);grant=await s.get(Grant,ids[3])
        if step=='PUBLISH':job.state='WAITING_MEDIA';job.container_id='200';d.state='WAITING_MEDIA'
        if change=='revoked':decision.state='REVOKED'
        if change=='expired':decision.expires_at=decisions.now()-timedelta(seconds=1)
        if change=='grant-revoked':grant.state='REVOKED'
        if change=='grant-expired':grant.expires_at=decisions.now()-timedelta(seconds=1)
        if change=='grant-hash':grant.sha256='f'*64
        if change=='grant-too-long':grant.created_at=grant.expires_at-timedelta(seconds=901)
        if change=='connection':(await s.get(Connection,1)).enabled=False
        if change=='copy':(await s.get(Copy,(job.artifact_id,'instagram'))).version+=1
        if change=='selection':(await s.get(Selection,job.artifact_id)).platforms=['facebook']
        if change=='source':(await s.get(Artifact,job.artifact_id)).review_status='DRAFT'
        if change=='evidence':decision.evidence_ref='external-email:unverified'
        if change=='snapshot':decision.snapshot={**decision.snapshot,'caption':'changed'}
        if change=='private-batch':job.connection_binding={**job.connection_binding,'login_mode':'PRIVATE_BATCH_UNIFIED'}
        if change=='unknown':job.state='PUBLISH_UNKNOWN' if step=='PUBLISH' else 'CREATE_UNKNOWN'
        if change=='grant-foreign':
            # Use an existing different decision FK, rather than an invalid FK.
            foreign=Decision(execution_id=job.id,snapshot_hash='f'*64,snapshot={},evidence_ref='trusted-message:synthetic-only',state='REVOKED',created_at=decisions.now(),expires_at=decision.expires_at)
            s.add(foreign);await s.flush();grant.decision_id=foreign.id
        await s.commit()
    with pytest.raises(ValueError):await validate(ids,step)

@pytest.mark.asyncio
async def test_slow_bytes_expire_before_return_and_changed_bytes_fail(config,monkeypatch):
    ids=await setup(monkeypatch)
    original=flow.recheck_pinned_bytes
    async def slow(s,j):
        await original(s,j)
        monkeypatch.setattr(decisions,'now',lambda:ids[4]+timedelta(hours=1))
    monkeypatch.setattr(flow,'recheck_pinned_bytes',slow)
    with pytest.raises(ValueError):await validate(ids)

@pytest.mark.asyncio
async def test_row_contention_and_no_implicit_transaction(config,monkeypatch):
    ids=await setup(monkeypatch)
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await flow.validate_locked(s,ids[1],step='CREATE_CONTAINER',grant_id=ids[3])
    async with SessionFactory() as editor:
        job=await editor.get(Job,ids[0]);await editor.execute(select(Copy).where(Copy.artifact_id==job.artifact_id).with_for_update())
        with pytest.raises(DBAPIError):await validate(ids)
    assert (await validate(ids))[0].id==ids[1]

@pytest.mark.asyncio
async def test_autobegin_not_an_explicit_owned_boundary(config,monkeypatch):
    ids=await setup(monkeypatch)
    async with SessionFactory() as s:
        await s.execute(select(Job.id).limit(1))
        with pytest.raises(ValueError):await flow.validate_locked(s,ids[1],step='CREATE_CONTAINER',grant_id=ids[3])

@pytest.mark.asyncio
@pytest.mark.parametrize('step',['CREATE_CONTAINER','PUBLISH'])
async def test_private_bytes_are_reread_at_each_step(config,monkeypatch,step):
    ids=await setup(monkeypatch)
    if step=='PUBLISH':
        async with SessionFactory() as s:
            job=await s.get(Job,ids[0]);job.state='WAITING_MEDIA';job.container_id='200'
            (await s.get(Dispatch,ids[1])).state='WAITING_MEDIA';await s.commit()
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    class Changed:
        async def get_bytes(self,*a,**kw):return b'changed-private-bytes'
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Changed())
    with pytest.raises(ValueError):await validate(ids,step)
