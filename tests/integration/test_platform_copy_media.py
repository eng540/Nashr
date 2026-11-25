import io
from uuid import UUID
import httpx
import pytest
from PIL import Image
from sqlalchemy import select,func
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,PlatformCopyMediaModel,PublicationModel,ScheduleItemModel
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_media_scheduling import _media_artifact

@pytest.mark.parametrize("target",["instagram","facebook"])
@pytest.mark.asyncio
async def test_saved_jpeg_is_private_versioned_separate_and_selection_checked(monkeypatch,target):
    uid=await _media_artifact();stream=io.BytesIO();Image.new('RGB',(640,800),'blue').save(stream,format='PNG');source=stream.getvalue();objects={};puts=[]
    class Storage:
        async def get_bytes(self,uri,*,max_bytes):return objects.get(uri,source)
        async def put(self,*,key,content,content_type):
            uri='s3://synthetic/'+key;objects[uri]=content;puts.append(uri);return uri
        async def presign_get(self,uri,*,expires_seconds):return 'https://private.example/signed'
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid);fp=source_fingerprint(row);original=row.storage_uri;meta=dict(row.artifact_metadata)
        for platform in [target,'telegram']:
            session.add(PlatformCopyModel(artifact_id=uid,platform=platform,fields={'title':'','description':'حقول محفوظة','tags':[],'alt_text':''},source_fingerprint=fp,origin='USER_EDITED',version=1))
        await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        base=f'/api/artifacts/{uid}/platform-copies/{target}'
        preview=await c.post(base+'/jpeg-preview',json={'source_fingerprint':fp,'copy_version':1,'background':'#ffffff'});assert preview.status_code==200,preview.text
        body={'source_fingerprint':fp,'copy_version':1,'background':'#ffffff','expected_sha256':preview.json()['sha256']}
        assert (await c.post(base+'/media/jpeg',json={**body,'expected_sha256':'0'*64})).status_code==409
        assert not puts
        saved=await c.post(base+'/media/jpeg',json=body);assert saved.status_code==200,saved.text
        asset=saved.json()['selected_media_id'];assert saved.json()['copy_version']==2 and len(puts)==1
        # Ambiguous retry cannot silently bump version or replace a newer selection.
        assert (await c.post(base+'/media/jpeg',json=body)).status_code==409
        measured=await c.post(base+'/inspect-media?selected=true',json={});assert measured.status_code==200,measured.text
        assert measured.json()['measurements']['format']=='JPEG' and measured.json()['inspected_media_id']==asset
        saved_bytes=objects[puts[0]];objects[puts[0]]=b'changed bytes'
        assert (await c.post(base+'/inspect-media?selected=true',json={})).status_code==409
        objects[puts[0]]=saved_bytes
        history=(await c.get(base+'/media')).json();assert len(history['items'])==1 and not history['items'][0]['source_stale']
        assert (await c.get(base+f'/media/{asset}/url')).json()['url']=='https://private.example/signed'
        selection={'source_fingerprint':fp,'copy_version':2,'media_id':None}
        assert (await c.post(base+'/media/selection',json=selection)).status_code==200
        assert (await c.post(base+'/media/selection',json={**selection,'copy_version':3,'media_id':asset})).status_code==200
        # No second object for the exact derivative, but explicit re-save uses current version.
        assert (await c.post(base+'/media/jpeg',json={**body,'copy_version':4})).status_code==200
        assert len(puts)==1
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,uid);row.artifact_metadata={**row.artifact_metadata,'caption':'تغير'};await session.commit();newfp=source_fingerprint(row)
        assert (await c.get(base+'/media')).json()['items'][0]['source_stale']
        assert (await c.post(base+'/inspect-media?selected=true',json={})).status_code==409
        assert (await c.post(base+'/media/selection',json={'source_fingerprint':newfp,'copy_version':5,'media_id':asset})).status_code==409
        # Can recover stale copy by explicitly returning to original; text still requires its own review.
        assert (await c.post(base+'/media/selection',json={'source_fingerprint':newfp,'copy_version':5,'media_id':None})).status_code==200
        wrong=f'/api/artifacts/{uid}/platform-copies/telegram/media/{asset}/url'
        assert (await c.get(wrong)).status_code==409
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid);other=await session.get(PlatformCopyModel,(uid,'telegram'));copy=await session.get(PlatformCopyModel,(uid,target))
        assert row.storage_uri==original and row.kind=='IMAGE' and row.mime_type=='image/webp'
        assert other.version==1 and other.selected_media_id is None and copy.fields['description']=='حقول محفوظة'
        assert not (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id==uid))).scalars().all()
        assert not (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.artifact_id==uid))).scalars().all()
        assert (await session.scalar(select(func.count()).select_from(PlatformCopyMediaModel).where(PlatformCopyMediaModel.artifact_id==uid)))==1

@pytest.mark.asyncio
async def test_storage_failure_never_changes_selection_or_copy(monkeypatch):
    from app.infrastructure.artifact_storage import ArtifactStorageError
    uid=await _media_artifact();out=io.BytesIO();Image.new('RGB',(400,400),'red').save(out,format='PNG');data=out.getvalue()
    class Storage:
        async def get_bytes(self,*args,**kw):return data
        async def put(self,**kw):raise ArtifactStorageError('synthetic unavailable')
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid);fp=source_fingerprint(row)
        session.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={'title':'','description':'محفوظ','tags':[],'alt_text':''},source_fingerprint=fp,origin='UNCHANGED_ORIGINAL',version=1));await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        base=f'/api/artifacts/{uid}/platform-copies/instagram';body={'source_fingerprint':fp,'copy_version':1,'background':'#ffffff'}
        preview=(await c.post(base+'/jpeg-preview',json=body)).json()
        assert (await c.post(base+'/media/jpeg',json={**body,'expected_sha256':preview['sha256']})).status_code==502
    async with SessionFactory() as session:
        copy=await session.get(PlatformCopyModel,(uid,'instagram'))
        assert copy.version==1 and copy.selected_media_id is None
        assert not (await session.execute(select(PlatformCopyMediaModel).where(PlatformCopyMediaModel.artifact_id==uid))).scalars().all()

@pytest.mark.asyncio
async def test_concurrent_same_version_saves_select_only_once(monkeypatch):
    import asyncio
    uid=await _media_artifact();out=io.BytesIO();Image.new('RGB',(400,400),'red').save(out,format='PNG');data=out.getvalue();puts=[]
    class Storage:
        async def get_bytes(self,*args,**kw):return data
        async def put(self,*,key,**kw):
            await asyncio.sleep(.03);puts.append(key);return 's3://synthetic/'+key
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid);fp=source_fingerprint(row)
        session.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={'title':'','description':'محفوظ','tags':[],'alt_text':''},source_fingerprint=fp,origin='UNCHANGED_ORIGINAL',version=1));await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        base=f'/api/artifacts/{uid}/platform-copies/instagram';body={'source_fingerprint':fp,'copy_version':1,'background':'#ffffff'}
        preview=(await c.post(base+'/jpeg-preview',json=body)).json();body['expected_sha256']=preview['sha256']
        responses=await asyncio.gather(c.post(base+'/media/jpeg',json=body),c.post(base+'/media/jpeg',json=body))
        assert sorted(r.status_code for r in responses)==[200,409]
        assert len(puts)==1
