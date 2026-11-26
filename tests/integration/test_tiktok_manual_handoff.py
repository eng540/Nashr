import io
import json
import zipfile
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select, func
from app.main import app
from app.application.distribution_readiness import source_fingerprint
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.models import ArtifactModel, PlatformCopyModel, PublicationModel, ScheduleItemModel, TikTokConnectionModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_media_scheduling import _media_artifact

async def fixture(monkeypatch):
    uid=await _media_artifact()
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);row.kind='VIDEO';row.mime_type='video/mp4';fp=source_fingerprint(row)
        s.add(PlatformCopyModel(artifact_id=uid,platform='tiktok',source_fingerprint=fp,version=1,origin='USER_EDITED',fields={'description':'النص كامل $ دون قص\nثانٍ','title':'عنوان منفصل','tags':['وسم'],'alt_text':'محفوظ'}));await s.commit()
    class Storage:
        async def get_bytes(self,uri,*,max_bytes):return b'synthetic-original-video'
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    return uid,fp

@pytest.mark.asyncio
async def test_bundle_exact_private_no_execution_or_mutation(monkeypatch):
    uid,fp=await fixture(monkeypatch)
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);before=(row.storage_uri,dict(row.artifact_metadata),row.review_status)
        connections=await s.scalar(select(func.count()).select_from(TikTokConnectionModel))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        r=await c.get(f'/api/artifacts/{uid}/platform-copies/tiktok/manual-bundle',params={'copy_version':1,'source_fingerprint':fp})
        assert r.status_code==200,r.text
        assert r.headers['cache-control']=='no-store' and r.headers['content-type']=='application/zip'
        assert 'attachment;' in r.headers['content-disposition']
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert set(z.namelist())=={'video-original.mp4','caption.txt','README.txt','manifest.json'}
            assert z.read('video-original.mp4')==b'synthetic-original-video'
            assert z.read('caption.txt').decode()=='النص كامل $ دون قص\nثانٍ'
            manifest=json.loads(z.read('manifest.json'));assert not manifest['execution_authorized'] and not manifest['upload_performed'] and not manifest['publication_recorded']
            assert manifest['separate_fields']['title']=='عنوان منفصل'
        assert (await c.get(f'/api/artifacts/{uid}/platform-copies/tiktok/manual-bundle',params={'copy_version':2,'source_fingerprint':fp})).status_code==409
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);assert before==(row.storage_uri,dict(row.artifact_metadata),row.review_status)
        copy=await s.get(PlatformCopyModel,(uid,'tiktok'));assert copy.version==1 and copy.selected_media_id is None
        assert await s.scalar(select(func.count()).select_from(TikTokConnectionModel))==connections
        for model in [PublicationModel,ScheduleItemModel]:assert not (await s.execute(select(model).where(model.artifact_id==uid))).scalars().all()

@pytest.mark.asyncio
async def test_export_rechecks_after_slow_read_and_never_returns_stale(monkeypatch):
    uid,fp=await fixture(monkeypatch)
    class Storage:
        async def get_bytes(self,uri,*,max_bytes):
            async with SessionFactory() as s:
                c=await s.get(PlatformCopyModel,(uid,'tiktok'));c.fields={**c.fields,'description':'تغير'};c.version+=1;await s.commit()
            return b'synthetic'
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    from app.application.tiktok_manual_handoff import export_bundle
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await export_bundle(s,uid,1,fp)

@pytest.mark.asyncio
async def test_reject_unapproved_stale_wrong_media_or_missing_copy(monkeypatch):
    from app.application.tiktok_manual_handoff import export_bundle
    uid,fp=await fixture(monkeypatch)
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await export_bundle(s,uuid4(),1,fp)
        row=await s.get(ArtifactModel,uid);row.review_status='DRAFT';await s.commit()
        with pytest.raises(ValueError):await export_bundle(s,uid,1,fp)
        row.review_status='APPROVED';row.mime_type='video/webm';await s.commit()
        with pytest.raises(ValueError):await export_bundle(s,uid,1,source_fingerprint(row))
        row.mime_type='video/mp4';await s.commit()
        with pytest.raises(ValueError):await export_bundle(s,uid,1,'0'*64)

@pytest.mark.asyncio
async def test_oversize_and_selected_derivative_fail_closed(monkeypatch):
    from app.application import tiktok_manual_handoff as service
    uid,fp=await fixture(monkeypatch)
    monkeypatch.setattr(service,'MAX_BYTES',4)
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await service.export_bundle(s,uid,1,fp)
    # The selected-media FK is not changed; the guard is independently exercised on a read snapshot.
    monkeypatch.setattr(service,'MAX_BYTES',50*1024*1024)
    from app.infrastructure.database.models import PlatformCopyMediaModel
    import hashlib
    async with SessionFactory() as s:
        media_id=uuid4()
        s.add(PlatformCopyMediaModel(id=media_id,artifact_id=uid,platform='tiktok',source_fingerprint=fp,source_sha256='a'*64,sha256='b'*64,storage_uri='s3://private/derived',mime_type='video/mp4',recipe={},measurements={}))
        await s.flush();copy=await s.get(PlatformCopyModel,(uid,'tiktok'));copy.selected_media_id=media_id;await s.commit()
        with pytest.raises(ValueError):await service.export_bundle(s,uid,1,fp)
