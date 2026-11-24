import io
import httpx
import pytest
from PIL import Image
from sqlalchemy import select,func
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,PlatformMediaInspectionModel,PublicationModel,ScheduleItemModel
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_media_scheduling import _media_artifact

@pytest.mark.asyncio
async def test_saved_inspection_survives_read_and_marks_copy_source_probe_stale(monkeypatch):
    uid=await _media_artifact();stream=io.BytesIO();Image.new('RGB',(640,800),'red').save(stream,format='JPEG');data=stream.getvalue();reads=[]
    class Storage:
        async def get_bytes(self,*a,**kw):reads.append(1);return data
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid);row.kind='IMAGE';row.mime_type='image/jpeg';fp=source_fingerprint(row);original=row.storage_uri
        session.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={'title':'','description':'حقول خاصة','tags':[],'alt_text':''},source_fingerprint=fp,origin='USER_EDITED',version=1));await session.commit()
    base=f'/api/artifacts/{uid}/platform-copies/instagram/media-inspections'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        payload={'source_fingerprint':fp,'copy_version':1,'selected':True}
        assert (await client.post(base,json={**payload,'copy_version':9})).status_code==409 and not reads
        saved=await client.post(base,json=payload);assert saved.status_code==200,saved.text
        assert not saved.json()['stale'] and not saved.json()['execution_authorized']
        history=(await client.get(base)).json();assert len(history['items'])==1 and len(reads)==1
        assert history['items'][0]['result']['pending'] and history['items'][0]['sha256']==saved.json()['sha256']
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,uid);copy=await session.get(PlatformCopyModel,(uid,'instagram'))
            assert row.storage_uri==original and copy.version==1 and copy.fields['description']=='حقول خاصة'
            copy.version=2;await session.commit()
        assert (await client.get(base)).json()['items'][0]['stale']
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,uid);row.artifact_metadata={**row.artifact_metadata,'caption':'تغير'};await session.commit()
        result=(await client.get(base)).json()['items'][0]
        assert len(result['stale_reasons'])==2 and len(reads)==1
        monkeypatch.setattr('app.application.media_inspection_history.PROBE_VERSION','next')
        assert len((await client.get(base)).json()['items'][0]['stale_reasons'])==3
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(PlatformMediaInspectionModel).where(PlatformMediaInspectionModel.artifact_id==uid))==1
        assert not (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id==uid))).scalars().all()
        assert not (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.artifact_id==uid))).scalars().all()

@pytest.mark.asyncio
async def test_source_change_during_probe_does_not_persist_false_current_result(monkeypatch):
    from app.application.media_inspection_history import record_inspection
    uid=await _media_artifact()
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid);fp=source_fingerprint(row)
        session.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={'title':'','description':'خاص','tags':[],'alt_text':''},source_fingerprint=fp,origin='USER_EDITED',version=1));await session.commit()
    async def probe(*args,**kw):
        async with SessionFactory() as other:
            row=await other.get(ArtifactModel,uid);row.artifact_metadata={'caption':'changed'};await other.commit()
        return {'inspected_media_id':None,'sha256':'a'*64}
    monkeypatch.setattr('app.application.media_inspection_history.probe_platform_media',probe)
    async with SessionFactory() as session:
        with pytest.raises(ValueError,match='أثناء الفحص'):await record_inspection(session,uid,'instagram',fingerprint=fp,version=1,selected=True)
        await session.rollback()
        assert await session.scalar(select(func.count()).select_from(PlatformMediaInspectionModel).where(PlatformMediaInspectionModel.artifact_id==uid))==0

@pytest.mark.asyncio
async def test_selection_change_marks_record_stale_and_history_never_reads_storage(monkeypatch):
    from uuid import uuid4
    from app.application.media_inspection_history import describe
    from types import SimpleNamespace
    from datetime import datetime,timezone
    row=SimpleNamespace(kind='IMAGE',content='text',storage_uri='s3://test/artifacts/source.jpg',mime_type='image/jpeg',artifact_metadata={},review_status='APPROVED',status='AVAILABLE')
    asset=uuid4();copy=SimpleNamespace(version=1,selected_media_id=asset)
    record=SimpleNamespace(id=uuid4(),source_fingerprint=source_fingerprint(row),copy_version=1,media_id=asset,selected=True,sha256='a'*64,probe_version='2026-11-24.1',result={'pending':['unknown']},created_at=datetime.now(timezone.utc))
    assert not describe(row,copy,record)['stale']
    copy.selected_media_id=None
    assert describe(row,copy,record)['stale_reasons']==['تغير اختيار وسيط النسخة.']
