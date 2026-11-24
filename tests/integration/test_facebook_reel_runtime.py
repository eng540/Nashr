from datetime import timedelta
import pytest
from sqlalchemy import delete
from app.application import facebook_reel_runtime as r
from app.infrastructure.database.models import FacebookReelJobModel as Job
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_instagram_oauth import config,browser

@pytest.mark.asyncio
async def test_preview_approval_no_write_and_no_replay(config,monkeypatch):
    from uuid import uuid4
    from app.infrastructure.database.models import ArtifactModel
    uid=uuid4();facts=dict(artifact_id=str(uid),media_sha256='a'*64,caption='exact',size_bytes=10)
    b={'page_id':'123','page_name':'Page'}
    async def pinned(s,u):return facts,b'bytes'
    async def binding(s):return b
    monkeypatch.setattr(r,'pinned',pinned);monkeypatch.setattr(r,'binding',binding)
    async with SessionFactory() as s:
        # Real artifact fixture supplies the FK without disclosing media.
        from sqlalchemy import select
        a=(await s.execute(select(ArtifactModel).limit(1))).scalars().first()
        if not a:pytest.skip('Requires seeded artifact')
        facts['artifact_id']=str(a.id)
        d=await r.stage(s,a.id);j=await s.get(Job,d['id'] if False else __import__('uuid').UUID(d['id']))
        assert j.state=='DRAFT' and not j.evidence_ref
        with pytest.raises(ValueError):await r.valid(s,j)
        with pytest.raises(ValueError):await r.approve(s,j,'b'*64,'owner-session:12345678')
        await r.approve(s,j,d['snapshot_hash'],'owner-session:12345678')
        assert j.state=='APPROVED'
        class Provider:
            async def initialize(self,**kw):raise RuntimeError('lost reply')
        async def provider(*a):return Provider()
        monkeypatch.setattr(r,'provider',provider)
        with pytest.raises(RuntimeError):await r.process_one(s,j)
        assert j.state=='INITIALIZING'
        # Never eligible for another initialization just because request failed.
        await r.process_one(s,j);assert j.state=='INITIALIZING'
        await s.delete(j);await s.commit()

@pytest.mark.asyncio
async def test_auth_and_approval_explicit(config):
    from app.main import app
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.get('/api/connections/facebook/reels/00000000-0000-0000-0000-000000000000')).status_code==401
    async with browser() as c:
        u='/api/connections/facebook/reels/00000000-0000-0000-0000-000000000000/approve'
        body=dict(snapshot_hash='a'*64,exact_words_approved=True,public_page_approved=True,media_transfer_approved=False)
        assert (await c.post(u,json=body)).status_code==409
        assert (await c.post(u,json={**body,'media_transfer_approved':'yes'})).status_code==422
        assert (await c.post(u,json=body,headers={'Origin':'https://evil.invalid'})).status_code==403

@pytest.mark.asyncio
async def test_complete_lifecycle_claims_and_readback_no_second_upload(monkeypatch):
    from types import SimpleNamespace
    class Session:
        async def commit(self):pass
    s=Session();calls=[]
    j=SimpleNamespace(state='APPROVED',remote_session=None,snapshot={'media_sha256':'a'*64,'caption':'exact','connection':{'page_id':'123'}},updated_at=r.now(),permalink=None,error_code=None)
    async def valid(*a):return b'bytes'
    from app.adapters.publishing.facebook_reels import ReelSession
    class P:
        async def initialize(self,**kw):calls.append('init');assert j.state=='INITIALIZING';return ReelSession('123','456','https://rupload.facebook.com/video-upload/456','a'*64,5)
        async def upload(self,*a,**kw):calls.append('upload');assert j.state=='UPLOADING'
        async def finish(self,*a,**kw):calls.append('finish');assert j.state=='FINISHING'
        async def status(self,*a):return dict(state='OK',upload_complete=True,processing_complete=True,publishing_not_started=True,publishing_complete=j.state=='FINISH_ACCEPTED')
        async def _request(self,*a,**kw):return dict(id='456',description='exact',**{'from':{'id':'123'}},published=True,permalink_url='https://www.facebook.com/reel/456')
    async def provider(*a):return P()
    monkeypatch.setattr(r,'provider',provider);monkeypatch.setattr(r,'valid',valid)
    await r.process_one(s,j);assert j.state=='PUBLISHED' and calls==['init','upload','finish']
    await r.process_one(s,j);assert calls==['init','upload','finish']

@pytest.mark.asyncio
async def test_unknown_never_mutates_and_mismatched_result_not_published(monkeypatch):
    from types import SimpleNamespace
    from app.adapters.publishing.facebook_reels import ReelSession
    j=SimpleNamespace(state='OUTCOME_UNKNOWN',remote_session=__import__('dataclasses').asdict(ReelSession('123','456','https://rupload.facebook.com/video-upload/456','a'*64,5)),snapshot={'caption':'exact'},updated_at=r.now(),permalink=None)
    class S:
        async def commit(self):pass
    class P:
        async def status(self,*a):return dict(state='OK',publishing_complete=True)
        async def _request(self,*a,**kw):return dict(id='456',description='wrong',**{'from':{'id':'999'}},published=True,permalink_url='https://evil.invalid/456')
    async def provider(*a):return P()
    monkeypatch.setattr(r,'provider',provider)
    await r.process_one(S(),j);assert j.state=='OUTCOME_UNKNOWN' and j.permalink is None
