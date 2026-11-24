import pytest
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,InstagramExecutionModel
from app.infrastructure.database.session import SessionFactory
from app.application.distribution_readiness import source_fingerprint
from app.application import instagram_execution as flow
from app.adapters.publishing.instagram import ContainerState,InstagramProviderError
from tests.integration.test_media_scheduling import _media_artifact

async def seed():
    uid=await _media_artifact()
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);row.mime_type='image/jpeg';fp=source_fingerprint(row)
        s.add(PlatformCopyModel(artifact_id=uid,platform='instagram',source_fingerprint=fp,fields={'title':'','description':'تعليق صناعي فقط','tags':[],'alt_text':'وصف راجعه المستخدم'},origin='USER_EDITED',version=1));await s.commit()
        job=await flow.prepare(s,uid,account_id='100',media_sha256='b'*64,copy_version=1,fingerprint=fp)
        return uid,job.id

class Provider:
    account_id='100'
    def __init__(self):self.calls=[]
    async def create_container(self,**kw):self.calls.append('create');return '200'
    async def publish_container(self,id):self.calls.append('publish');return '300'
    async def container_status(self,id):self.calls.append('status');return ContainerState(id,'FINISHED')
    async def published_media(self,id):self.calls.append('media');return {'media_id':id,'permalink':'https://www.instagram.com/p/synthetic/','account_id':'100'}

@pytest.mark.asyncio
async def test_core_requires_explicit_authority_and_preserves_original():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);before=(row.content,dict(row.artifact_metadata),row.review_status,row.storage_uri)
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64)
        assert not p.calls
        job=await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True);assert job.state=='CONTAINER_CREATED'
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
        job=await flow.publish(s,jid,provider=p,media_sha256='b'*64,authorized=True);assert job.state=='PUBLISHED_ID_KNOWN'
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,media_sha256='b'*64,authorized=True)
        job=await flow.reconcile(s,jid,provider=p);assert job.state=='PUBLISHED' and job.permalink
        await s.refresh(row);assert (row.content,row.artifact_metadata,row.review_status,row.storage_uri)==before
    assert p.calls==['create','publish','media']

@pytest.mark.asyncio
async def test_unknown_creation_never_retries_or_exposes_grant_in_record():
    uid,jid=await seed()
    class Unknown(Provider):
        async def create_container(self,**kw):self.calls.append('create');raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN',outcome_unknown=True)
    p=Unknown()
    async with SessionFactory() as s:
        job=await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private-grant',media_sha256='b'*64,authorized=True)
        assert job.state=='CREATE_UNKNOWN' and job.container_id is None
        assert 'private-grant' not in str(vars(job))
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private-grant',media_sha256='b'*64,authorized=True)
    assert p.calls==['create']

@pytest.mark.asyncio
async def test_unknown_publish_only_reconciles_without_resending():
    uid,jid=await seed()
    class Unknown(Provider):
        async def publish_container(self,id):self.calls.append('publish');raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN',outcome_unknown=True)
        async def container_status(self,id):self.calls.append('status');return ContainerState(id,'PUBLISHED')
    p=Unknown()
    async with SessionFactory() as s:
        await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
        job=await flow.publish(s,jid,provider=p,media_sha256='b'*64,authorized=True);assert job.state=='PUBLISH_UNKNOWN'
        job=await flow.reconcile(s,jid,provider=p);assert job.state=='PUBLISHED_ID_UNKNOWN'
        with pytest.raises(ValueError):await flow.publish(s,jid,provider=p,media_sha256='b'*64,authorized=True)
    assert p.calls==['create','publish','status']

@pytest.mark.asyncio
async def test_stale_copy_or_wrong_account_prevents_provider_calls():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='c'*64,authorized=True)
        copy=await s.get(PlatformCopyModel,(uid,'instagram'));copy.version+=1;await s.commit()
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
    assert not p.calls

@pytest.mark.asyncio
async def test_concurrent_create_claim_only_calls_provider_once():
    import asyncio
    uid,jid=await seed();p=Provider()
    async def attempt():
        async with SessionFactory() as s:
            try:return await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
            except ValueError:return None
    await asyncio.gather(attempt(),attempt())
    assert p.calls==['create']


@pytest.mark.asyncio
async def test_cancel_unclaimed_draft_does_not_cancel_or_retry_provider_attempts():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        job=await flow.cancel_draft(s,jid);assert job.state=='CANCELLED'
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
        with pytest.raises(ValueError):await flow.reconcile(s,jid,provider=p)
    assert p.calls==[]

@pytest.mark.asyncio
async def test_interrupted_claim_requires_operator_and_exact_observed_version():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        job=await s.get(InstagramExecutionModel,jid);job.state='CREATING';await s.commit();stamp=job.updated_at
        with pytest.raises(ValueError):await flow.mark_interrupted_claim_unknown(s,jid,expected_state='CREATING',expected_updated_at=stamp)
        with pytest.raises(ValueError):await flow.mark_interrupted_claim_unknown(s,jid,expected_state='PUBLISHING',expected_updated_at=stamp,operator_confirmed_stopped=True)
        job=await flow.mark_interrupted_claim_unknown(s,jid,expected_state='CREATING',expected_updated_at=stamp,operator_confirmed_stopped=True)
        assert job.state=='CREATE_UNKNOWN' and job.container_id is None
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
        with pytest.raises(ValueError):await flow.cancel_draft(s,jid)
    assert p.calls==[]

@pytest.mark.asyncio
async def test_publish_read_failure_is_waiting_without_retrying_a_mutation():
    uid,jid=await seed()
    class ReadingFailure(Provider):
        async def publish_container(self,id):self.calls.append('read-failed');raise InstagramProviderError('INSTAGRAM_READ_FAILED')
    p=ReadingFailure()
    async with SessionFactory() as s:
        await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
        job=await flow.publish(s,jid,provider=p,media_sha256='b'*64,authorized=True)
        assert job.state=='WAITING_MEDIA'
    assert p.calls==['create','read-failed']

@pytest.mark.asyncio
async def test_concurrent_publish_claim_has_one_provider_mutation():
    import asyncio
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a.jpg',media_sha256='b'*64,authorized=True)
    async def attempt():
        async with SessionFactory() as s:
            try:return await flow.publish(s,jid,provider=p,media_sha256='b'*64,authorized=True)
            except ValueError:return None
    await asyncio.gather(attempt(),attempt())
    assert p.calls==['create','publish']
