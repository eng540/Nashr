import pytest
from sqlalchemy import select,func
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,InstagramExecutionModel,PlatformMediaInspectionModel
from app.application import instagram_execution as flow
from app.application.distribution_readiness import source_fingerprint
from app.application.media_inspection_history import record_inspection
from app.infrastructure.artifact_storage import S3ArtifactStorage
from tests.integration.test_instagram_execution_core import seed,Provider,MEDIA,DIGEST,private_storage
from tests.integration.test_media_scheduling import _media_artifact
from uuid import UUID,uuid4


@pytest.mark.asyncio
async def test_missing_or_unrelated_inspection_cannot_prepare():
    uid,jid=await seed()
    async with SessionFactory() as s:
        job=await s.get(InstagramExecutionModel,jid)
        args=dict(account_id='100',media_sha256=DIGEST,copy_version=1,fingerprint=job.source_fingerprint)
        with pytest.raises(ValueError,match='inspection'):await flow.prepare(s,uid,**args)
        with pytest.raises(ValueError):await flow.prepare(s,uid,inspection_id=uuid4(),**args)
        with pytest.raises(ValueError):await flow.prepare(s,uid,inspection_id=job.inspection_id,**{**args,'media_sha256':'a'*64})


@pytest.mark.asyncio
@pytest.mark.parametrize('before_publish',[False,True])
async def test_mutated_bytes_stop_provider_before_create_or_publish(monkeypatch,before_publish):
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        if before_publish:
            await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private',media_sha256=DIGEST,authorized=True)
        class Changed:
            async def get_bytes(self,*args,**kw):return MEDIA+b'changed'
        monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Changed())
        with pytest.raises(ValueError,match='differs'):
            if before_publish:await flow.publish(s,jid,provider=p,media_sha256=DIGEST,authorized=True)
            else:await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private',media_sha256=DIGEST,authorized=True)
        job=await s.get(InstagramExecutionModel,jid)
        assert job.state==('CONTAINER_CREATED' if before_publish else 'DRAFT')
        assert p.calls==(['create'] if before_publish else [])


@pytest.mark.asyncio
async def test_old_uninspected_draft_is_fail_closed():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        job=await s.get(InstagramExecutionModel,jid);job.inspection_id=None;await s.commit()
        with pytest.raises(ValueError,match='Uninspected'):
            await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private',media_sha256=DIGEST,authorized=True)
        assert not p.calls and job.state=='DRAFT'


@pytest.mark.asyncio
async def test_changed_probe_version_or_selection_refuses_provider(monkeypatch):
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        monkeypatch.setattr('app.application.instagram_media_pin.PROBE_VERSION','changed')
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private',media_sha256=DIGEST,authorized=True)
        assert not p.calls


@pytest.mark.asyncio
async def test_tampered_saved_evidence_cannot_prepare_or_execute():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        job=await s.get(InstagramExecutionModel,jid);record=await s.get(PlatformMediaInspectionModel,job.inspection_id)
        record.result={**record.result,'blockers':['unsupported']};await s.commit()
        with pytest.raises(ValueError):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private',media_sha256=DIGEST,authorized=True)
        assert not p.calls


@pytest.mark.asyncio
async def test_changed_caption_without_version_bump_stops_provider():
    uid,jid=await seed();p=Provider()
    async with SessionFactory() as s:
        copy=await s.get(PlatformCopyModel,(uid,'instagram'));copy.fields={**copy.fields,'description':'different'};await s.commit()
        with pytest.raises(ValueError,match='fields'):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/private',media_sha256=DIGEST,authorized=True)
        assert not p.calls

@pytest.mark.asyncio
async def test_private_selected_jpeg_pinned_not_original(monkeypatch):
    from app.infrastructure.database.models import PlatformCopyMediaModel
    from app.application.platform_copy_media import select_media
    uid,jid=await seed();p=Provider();asset_id=uuid4();reads=[]
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);fp=source_fingerprint(row)
        s.add(PlatformCopyMediaModel(id=asset_id,artifact_id=uid,platform='instagram',source_fingerprint=fp,
            source_sha256='a'*64,sha256=DIGEST,storage_uri='s3://synthetic/selected.jpg',mime_type='image/jpeg',recipe={},measurements={}))
        await s.commit()
        await select_media(s,uid,'instagram',fingerprint=fp,version=1,media_id=asset_id)
    class Storage:
        async def get_bytes(self,uri,**kw):reads.append(uri);return MEDIA
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    async with SessionFactory() as s:
        evidence=await record_inspection(s,uid,'instagram',fingerprint=fp,version=2,selected=True)
        job=await flow.prepare(s,uid,account_id='100',media_sha256=DIGEST,copy_version=2,fingerprint=fp,inspection_id=UUID(evidence['id']))
        await flow.create_container(s,job.id,provider=p,media_url='https://synthetic.example/selected',media_sha256=DIGEST,authorized=True)
        assert p.calls==['create'] and reads==['s3://synthetic/selected.jpg']*2
        await select_media(s,uid,'instagram',fingerprint=fp,version=2,media_id=None)
        with pytest.raises(ValueError):await flow.publish(s,job.id,provider=p,media_sha256=DIGEST,authorized=True)
        assert p.calls==['create']


@pytest.mark.asyncio
async def test_unauthorized_attempt_never_reads_private_bytes(monkeypatch):
    uid,jid=await seed();p=Provider()
    class NoReads:
        async def get_bytes(self,*a,**kw):raise AssertionError('No private read without authority')
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:NoReads())
    async with SessionFactory() as s:
        with pytest.raises(ValueError,match='authority'):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a',media_sha256=DIGEST)
        p.account_id='101'
        with pytest.raises(ValueError,match='account'):await flow.create_container(s,jid,provider=p,media_url='https://synthetic.example/a',media_sha256=DIGEST,authorized=True)
        assert not p.calls
