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

@pytest.mark.asyncio
async def test_private_delivery_keeps_exact_video_timing(monkeypatch):
    import subprocess,tempfile,hashlib
    from pathlib import Path
    from types import SimpleNamespace
    from uuid import uuid4
    from app.application import platform_copy_media
    from app.domain.platform_media_probe import inspect_media
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=540x960:rate=24:duration=3.5','-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=3.5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart','-use_editlist','0',str(path)],check=True,capture_output=True)
        source=path.read_bytes()
    uid=uuid4();a=SimpleNamespace(kind='VIDEO',storage_uri='private-source');fb=SimpleNamespace(version=1,fields={},selected_media_id=None);ig=SimpleNamespace(selected_media_id=None,source_fingerprint='fp',fields={'description':'exact\n\ncaption'})
    class Scalar:
        def scalars(self):return self
        def first(self):return None
    class Session:
        async def get(self,model,key):return a if model is r.ArtifactModel else ig if key[1]=='instagram' else fb
        async def execute(self,*a):return Scalar()
        async def commit(self):pass
        def add(self,x):self.asset=x
    s=Session();saved={}
    class Storage:
        async def get_bytes(self,*a,**kw):return source
        async def put(self,**kw):saved['content']=kw['content'];return 'private-derivative'
    async def current_copy(*a):return a0,fb
    a0=a
    monkeypatch.setattr(platform_copy_media,'current_copy',current_copy)
    monkeypatch.setattr(r,'source_fingerprint',lambda a:'fp')
    monkeypatch.setattr(r.S3ArtifactStorage,'from_environment',lambda:Storage())
    result=await r.prepare_delivery(s,uid)
    m=inspect_media(saved['content'],'VIDEO','video/mp4')
    assert m['fps']==24 and m['width']==540 and m['height']==960
    assert m['audio'][0]['sample_rate']==48000 and m['audio'][0]['channels']==2
    assert s.asset.recipe['version']==2 and fb.fields==ig.fields
    assert result['video_packets_identical'] and result['published'] is False

@pytest.mark.asyncio
async def test_provider_evidence_requires_owner(config):
    from app.main import app
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.get('/api/connections/facebook/reels/00000000-0000-0000-0000-000000000000/provider-status')).status_code==401

@pytest.mark.asyncio
async def test_retirement_preserves_status_and_rejects_publishing(monkeypatch):
    from types import SimpleNamespace
    j=SimpleNamespace(state='OUTCOME_UNKNOWN',remote_session={'video_id':'456'},updated_at=r.now())
    st={'video_status':'uploading','processing_phase':{'status':'not_started'},'publishing_phase':{'status':'not_started'}}
    class P:
        async def _request(self,*a,**k):return {'status':st}
    async def provider(*a):return P()
    monkeypatch.setattr(r,'provider',provider);monkeypatch.setattr(r,'describe',lambda j:{'state':j.state})
    class S:
        async def commit(self):pass
    st['publishing_phase']['status']='in_progress'
    with pytest.raises(ValueError):await r.retire_unfinished(S(),j)
    assert j.state=='OUTCOME_UNKNOWN'
    st['publishing_phase']['status']='not_started'
    await r.retire_unfinished(S(),j)
    assert j.state=='RETIRED_UNPUBLISHED' and j.remote_session['never_resume'] is True and j.remote_session['retired_status_evidence']==st
    with pytest.raises(ValueError):await r.retire_unfinished(S(),j)
