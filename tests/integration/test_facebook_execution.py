import asyncio
import hashlib
import pytest
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel
from app.application.distribution_readiness import source_fingerprint
from app.application import facebook_execution as flow
from app.adapters.publishing.facebook import FacebookResult,FacebookProviderError
from tests.integration.test_media_scheduling import _media_artifact

CONTENT=b'synthetic photo not uploaded'
AUTH=dict(authorized=True,public_page_acknowledged=True,rights_confirmed=True,prerequisites_verified=True)

async def seed(kind='TEXT'):
    uid=await _media_artifact()
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);row.kind=kind
        row.mime_type='image/jpeg' if kind=='IMAGE' else 'text/plain'
        s.add(PlatformCopyModel(artifact_id=uid,platform='facebook',source_fingerprint=source_fingerprint(row),fields={'title':'','description':'نص كامل غير مختصر','tags':[],'alt_text':''},origin='USER_EDITED',version=1))
        await s.commit()
        job=await flow.prepare(s,uid,page_id='123',**(dict(media_sha256=hashlib.sha256(CONTENT).hexdigest(),total_bytes=len(CONTENT)) if kind=='IMAGE' else {}))
        return uid,job.id

class Provider:
    page_id='123'
    def __init__(self):self.calls=[]
    async def publish_text(self,**kw):
        self.calls.append('text');assert kw['message']=='نص كامل غير مختصر';return FacebookResult('POST_ID_KNOWN','123_456')
    async def publish_photo(self,**kw):
        self.calls.append('photo');assert kw['content']==CONTENT;return FacebookResult('POST_ID_KNOWN','123_456','789')
    async def verify_post(self,post_id,**kw):
        self.calls.append('verify');return FacebookResult('PUBLISHED_AT_LAST_CHECK',post_id,permalink='https://www.facebook.com/synthetic-test')

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['TEXT','IMAGE'])
async def test_claim_once_and_readback(kind):
    uid,jid=await seed(kind);p=Provider();content=CONTENT if kind=='IMAGE' else None
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,content=content)
        job=await flow.publish(s,jid,provider=p,content=content,**AUTH);assert job.state=='POST_ID_KNOWN'
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,content=content,**AUTH)
        with pytest.raises(ValueError):await flow.cancel_draft(s,jid)
        job=await flow.reconcile(s,jid,provider=p);assert job.state=='PUBLISHED_AT_LAST_CHECK'
    assert p.calls==[kind.lower() if kind=='TEXT' else 'photo','verify']

@pytest.mark.asyncio
async def test_unknown_never_retries_or_invents_identity():
    uid,jid=await seed()
    class Lost(Provider):
        async def publish_text(self,**kw):self.calls.append('text');raise FacebookProviderError('FACEBOOK_OUTCOME_UNKNOWN',outcome_unknown=True)
    p=Lost()
    async with SessionFactory() as s:
        job=await flow.publish(s,jid,provider=p,**AUTH);assert job.state=='OUTCOME_UNKNOWN' and job.post_id is None
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,**AUTH)
        with pytest.raises(ValueError):await flow.reconcile(s,jid,provider=p)
    assert p.calls==['text']

@pytest.mark.asyncio
async def test_changed_copy_and_wrong_page_prevent_edge():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        p.page_id='999'
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,**AUTH)
        p.page_id='123';copy=await s.get(PlatformCopyModel,(uid,'facebook'));copy.fields={**copy.fields,'description':'تغيير'};await s.commit()
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,**AUTH)
    assert p.calls==[]

@pytest.mark.asyncio
async def test_changed_bytes_and_missing_prerequisites_prevent_edge():
    uid,jid=await seed('IMAGE');p=Provider()
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,content=CONTENT+b'x',**AUTH)
        for key in AUTH:
            with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,content=CONTENT,**{**AUTH,key:False})
    assert p.calls==[]

@pytest.mark.asyncio
async def test_local_cancel_and_interrupted_claim_fencing():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        job=await flow.cancel_draft(s,jid)
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,**AUTH)
    uid,jid=await seed()
    async with SessionFactory() as s:
        job=await flow.locked(s,jid);job.state='SENDING';await s.commit();stamp=job.updated_at
        with pytest.raises(ValueError):await flow.interrupted_claim(s,jid,expected_updated_at=stamp)
        with pytest.raises(ValueError):await flow.reconcile(s,jid,provider=p)
        job=await flow.interrupted_claim(s,jid,expected_updated_at=stamp,worker_confirmed_stopped=True);assert job.state=='OUTCOME_UNKNOWN'
        with pytest.raises(ValueError):await flow.interrupted_claim(s,jid,expected_updated_at=stamp,worker_confirmed_stopped=True)
    assert p.calls==[]

@pytest.mark.asyncio
async def test_concurrent_attempts_only_one_external_call():
    uid,jid=await seed();p=Provider()
    async def run():
        async with SessionFactory() as s:
            try:return (await flow.publish(s,jid,provider=p,**AUTH)).state
            except ValueError:return 'blocked'
    results=await asyncio.gather(run(),run())
    assert sorted(results)==['POST_ID_KNOWN','blocked'] and p.calls==['text']

@pytest.mark.asyncio
async def test_alt_text_is_not_silently_ignored():
    uid,jid=await seed('IMAGE');p=Provider()
    async with SessionFactory() as s:
        copy=await s.get(PlatformCopyModel,(uid,'facebook'));copy.fields={**copy.fields,'alt_text':'مطلوب'};await s.commit()
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,content=CONTENT,**AUTH)
    assert p.calls==[]

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('title','عنوان'),('tags',['وسم'])])
async def test_unimplemented_fields_are_not_silently_discarded(field,value):
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        copy=await s.get(PlatformCopyModel,(uid,'facebook'));copy.fields={**copy.fields,field:value};await s.commit()
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,**AUTH)
    assert p.calls==[]

@pytest.mark.asyncio
async def test_malformed_success_cannot_become_completed():
    uid,jid=await seed()
    class Malformed(Provider):
        async def publish_text(self,**kw):return FacebookResult('POST_ID_KNOWN','999_456')
    async with SessionFactory() as s:
        job=await flow.publish(s,jid,provider=Malformed(),**AUTH)
        assert job.state=='OUTCOME_UNKNOWN' and job.post_id is None

@pytest.mark.asyncio
async def test_definite_failure_still_cannot_automatically_resubmit():
    uid,jid=await seed()
    class Denied(Provider):
        async def publish_text(self,**kw):self.calls.append('text');raise FacebookProviderError('FACEBOOK_RECONNECT_REQUIRED')
    p=Denied()
    async with SessionFactory() as s:
        job=await flow.publish(s,jid,provider=p,**AUTH);assert job.state=='FAILED'
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,**AUTH)
    assert p.calls==['text']
