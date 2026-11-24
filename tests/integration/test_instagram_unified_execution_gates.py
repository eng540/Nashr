from datetime import timedelta
from uuid import UUID
import pytest
from app.application import instagram_publish_decisions as decisions,instagram_media_grants as grants,instagram_dispatch as dispatch,instagram_unified_execution as direct,instagram_execution as core
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramPublishDecisionModel as Decision,InstagramMediaGrantModel as Grant
from tests.integration.test_instagram_unified_execution_drafts import setup
from tests.integration.test_instagram_execution_core import private_storage,Provider,MEDIA
from tests.integration.test_instagram_oauth import config

async def approved(monkeypatch):
    uid,rid=await setup(monkeypatch)
    async with SessionFactory() as s:
        j=await direct.stage(s,uid,rid);jid=UUID(j['id']);due=decisions.now()+timedelta(seconds=30)
        p=await decisions.proposal(s,jid,due_at=due,timezone_name='Asia/Riyadh')
        d=await decisions.record(s,jid,decision_hash=p['decision_hash'],due_at=due,timezone_name='Asia/Riyadh',evidence_ref='trusted-message:synthetic-only-123',authenticated_owner=True,exact_words_approved=True,public_post_approved=True,media_disclosure_approved=True)
        return jid,d.id,due

@pytest.mark.asyncio
async def test_exact_decision_separate_from_review_and_each_consent(config,monkeypatch):
    uid,rid=await setup(monkeypatch)
    async with SessionFactory() as s:
        j=await direct.stage(s,uid,rid);jid=UUID(j['id']);due=decisions.now()+timedelta(minutes=1)
        p=await decisions.proposal(s,jid,due_at=due,timezone_name='Asia/Riyadh');assert not p['approval_recorded']
        assert '15_MINUTES' in p['media_disclosure'] and p['audience']=='INSTAGRAM_PUBLIC_POST'
        base=dict(decision_hash=p['decision_hash'],due_at=due,timezone_name='Asia/Riyadh',evidence_ref='trusted-message:synthetic-only-123',authenticated_owner=True,exact_words_approved=True,public_post_approved=True,media_disclosure_approved=True)
        for field in ['authenticated_owner','exact_words_approved','public_post_approved','media_disclosure_approved']:
            with pytest.raises(ValueError):await decisions.record(s,jid,**{**base,field:False})
        with pytest.raises(ValueError):await decisions.record(s,jid,**{**base,'decision_hash':'a'*64})
        with pytest.raises(ValueError):await decisions.record(s,jid,**{**base,'evidence_ref':'untrusted-email'})
        d=await decisions.record(s,jid,**base);assert (await decisions.record(s,jid,**base)).id==d.id

@pytest.mark.asyncio
async def test_media_not_early_expiring_revocable_and_only_pinned_bytes(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        with pytest.raises(ValueError,match='before'):await grants.mint(s,jid,did)
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
        g,token=await grants.mint(s,jid,did);assert token not in str(vars(g))
        assert (await grants.read(s,token))[0]==MEDIA
        with pytest.raises(ValueError):await grants.read(s,'x'*43)
        await decisions.revoke(s,did)
        with pytest.raises(ValueError):await grants.read(s,token)

@pytest.mark.asyncio
async def test_expiry_stops_media_and_no_duplicate_grant(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1));g,token=await grants.mint(s,jid,did,token_seconds=1)
        with pytest.raises(ValueError):await grants.mint(s,jid,did)
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=3))
        with pytest.raises(ValueError):await grants.read(s,token)

@pytest.mark.asyncio
async def test_due_dispatch_disabled_by_default_and_one_attempt(config,monkeypatch):
    jid,did,due=await approved(monkeypatch);p=Provider();p.graph_base='https://graph.facebook.com/v27.0'
    async with SessionFactory() as s:
        job=await dispatch.schedule(s,jid,did);assert (await dispatch.schedule(s,jid,did)).id==job.id
        assert await dispatch.due_ids(s)==[]
        with pytest.raises(ValueError,match='disabled'):await dispatch.run(s,job.id,provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/a')
        assert not p.calls
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
        assert await dispatch.due_ids(s)==[job.id]
        result=await dispatch.run(s,job.id,provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/a',runtime_enabled=True)
        assert result.state=='RESULT_KNOWN' and p.calls==['create','publish']
        with pytest.raises(ValueError):await dispatch.run(s,job.id,provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/a',runtime_enabled=True)
        assert (await dispatch.reconcile(s,job.id,provider=p)).state=='PUBLISHED'
        assert p.calls==['create','publish','media']

@pytest.mark.asyncio
async def test_revocation_cancels_pending_dispatch_without_effect(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        row=await dispatch.schedule(s,jid,did);await decisions.revoke(s,did);await s.refresh(row);assert row.state=='CANCELLED'

@pytest.mark.asyncio
async def test_waiting_media_keeps_bounded_grant_then_resumes_once(config,monkeypatch):
    from app.adapters.publishing.instagram import InstagramProviderError
    from sqlalchemy import select
    jid,did,due=await approved(monkeypatch)
    class Waiting(Provider):
        graph_base='https://graph.facebook.com/v27.0'
        async def publish_container(self,container):
            self.calls.append('publish-check')
            if self.calls.count('publish-check')==1:raise InstagramProviderError('INSTAGRAM_CONTAINER_IN_PROGRESS')
            return '300'
    p=Waiting()
    async with SessionFactory() as s:
        row=await dispatch.schedule(s,jid,did);monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
        result=await dispatch.run(s,row.id,provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/a',runtime_enabled=True);assert result.state=='WAITING_MEDIA'
        grant=(await s.execute(select(Grant).where(Grant.execution_id==jid))).scalar_one();assert grant.state=='ACTIVE'
        result=await dispatch.resume_media(s,row.id,provider=p,runtime_enabled=True);assert result.state=='RESULT_KNOWN'
        await s.refresh(grant);assert grant.state=='REVOKED'
        with pytest.raises(ValueError):await dispatch.resume_media(s,row.id,provider=p,runtime_enabled=True)
        assert p.calls==['create','publish-check','publish-check']

@pytest.mark.asyncio
async def test_unknown_container_no_retry_grant_revoked(config,monkeypatch):
    from app.adapters.publishing.instagram import InstagramProviderError
    from sqlalchemy import select
    jid,did,due=await approved(monkeypatch)
    class Unknown(Provider):
        graph_base='https://graph.facebook.com/v27.0'
        async def create_container(self,**kw):self.calls.append('create');raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN',outcome_unknown=True)
    p=Unknown()
    async with SessionFactory() as s:
        row=await dispatch.schedule(s,jid,did);monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
        result=await dispatch.run(s,row.id,provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/a',runtime_enabled=True);assert result.state=='RECONCILE_ONLY'
        grant=(await s.execute(select(Grant).where(Grant.execution_id==jid))).scalar_one();assert grant.state=='REVOKED'
        with pytest.raises(ValueError):await dispatch.run(s,row.id,provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/a',runtime_enabled=True)
        assert p.calls==['create']

@pytest.mark.asyncio
async def test_changed_bytes_do_not_escape_capability(config,monkeypatch):
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1));g,token=await grants.mint(s,jid,did)
        class Storage:
            async def get_bytes(self,*a,**kw):return b'changed'
        monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
        with pytest.raises(ValueError):await grants.read(s,token)

@pytest.mark.asyncio
async def test_no_registered_effect_or_capability_routes():
    from app.main import app
    paths=list(app.openapi()['paths'])
    assert not any('instagram' in p and any(s in p for s in ['capability','media-grant','/publish']) for p in paths)
    assert '/instagram-media' not in paths

@pytest.mark.asyncio
async def test_dispatch_requires_stopped_worker_before_interrupted_recovery(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        row=await dispatch.schedule(s,jid,did);row.state='CLAIMED';await s.commit();stamp=row.updated_at
        with pytest.raises(ValueError):await dispatch.interrupted(s,row.id,expected_updated_at=stamp)
        await dispatch.interrupted(s,row.id,expected_updated_at=stamp,worker_confirmed_stopped=True)
        assert row.state=='RECONCILE_ONLY'

@pytest.mark.asyncio
async def test_decision_change_and_cancelled_review_invalidate_media(config,monkeypatch):
    from app.infrastructure.database.models import InstagramExecutionModel as Job
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1));g,token=await grants.mint(s,jid,did)
        job=await s.get(Job,jid);job.caption='different outgoing words';await s.commit()
        with pytest.raises(ValueError,match='changed'):await grants.read(s,token)

@pytest.mark.asyncio
async def test_wrong_provider_host_never_claims_or_exposes_media(config,monkeypatch):
    jid,did,due=await approved(monkeypatch);p=Provider();p.graph_base='https://graph.instagram.com/v27.0'
    async with SessionFactory() as s:
        row=await dispatch.schedule(s,jid,did);monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
        with pytest.raises(ValueError,match='host'):await dispatch.run(s,row.id,provider=p,grant_url_factory=lambda *a:'https://synthetic.invalid/a',runtime_enabled=True)
        assert row.state=='PENDING' and not p.calls

@pytest.mark.asyncio
async def test_unified_reconnect_revokes_existing_exact_decision(config,monkeypatch):
    from app.infrastructure.database.models import InstagramConnectionModel
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        conn=await s.get(InstagramConnectionModel,1);conn.connected_at=decisions.now();await s.commit()
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
        with pytest.raises(ValueError):await grants.mint(s,jid,did)
