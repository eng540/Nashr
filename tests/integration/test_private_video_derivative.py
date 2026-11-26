import pytest
from uuid import UUID
import httpx
from sqlalchemy import select,func
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,PlatformCopyMediaModel,PublicationModel,ScheduleItemModel
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_media_scheduling import _media_artifact

@pytest.mark.parametrize('target',['instagram','facebook'])
@pytest.mark.asyncio
async def test_video_saved_private_unselected_without_duplicate_original_or_approval(monkeypatch,target):
 uid=await _media_artifact();objects={};puts=[]
 class Storage:
  async def get_bytes(self,*a,**kw):return b'original-video'
  async def put(self,*,key,content,content_type):
   uri='s3://synthetic/'+key;objects[uri]=content;puts.append(uri);return uri
 monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
 monkeypatch.setattr('app.domain.video_derivative.video_derivative',lambda data,platform:(b'derivative-'+platform.encode(),{'width':1080,'height':1920}))
 async with SessionFactory() as s:
  row=await s.get(ArtifactModel,uid);row.kind='VIDEO';row.mime_type='video/mp4';fp=source_fingerprint(row);uri=row.storage_uri
  s.add(PlatformCopyModel(artifact_id=uid,platform=target,fields={'title':'','description':'محفوظ','tags':[],'alt_text':''},source_fingerprint=fp,origin='UNCHANGED_ORIGINAL',version=1));await s.commit()
  before=await s.scalar(select(func.count()).select_from(ArtifactModel))
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
  base=f'/api/artifacts/{uid}/platform-copies/{target}'
  body={'source_fingerprint':fp,'copy_version':1,'full_frame_black_padding':True}
  assert (await c.post(base+'/media/video',json={**body,'full_frame_black_padding':False})).status_code==409
  assert not puts
  r=await c.post(base+'/media/video',json=body);assert r.status_code==200,r.text
  assert r.json()['selected'] is False and r.json()['selected_media_id'] is None
  mid=r.json()['media']['id']
  assert (await c.post(base+'/media/video',json=body)).status_code==200
  assert len(puts)==1
  assert (await c.post(base+'/media/selection',json={'source_fingerprint':fp,'copy_version':1,'media_id':mid})).status_code==200
  assert (await c.post(base+'/media/video',json=body)).status_code==409
 async with SessionFactory() as s:
  row=await s.get(ArtifactModel,uid);copy=await s.get(PlatformCopyModel,(uid,target));asset=await s.get(PlatformCopyMediaModel,UUID(mid))
  assert row.storage_uri==uri and row.review_status=='APPROVED' and copy.fields['description']=='محفوظ'
  assert copy.version==2 and copy.selected_media_id==asset.id and not asset.recipe['cropped']
  assert await s.scalar(select(func.count()).select_from(ArtifactModel))==before
  assert not (await s.execute(select(PublicationModel).where(PublicationModel.artifact_id==uid))).scalars().all()
  assert not (await s.execute(select(ScheduleItemModel).where(ScheduleItemModel.artifact_id==uid))).scalars().all()

@pytest.mark.asyncio
async def test_source_change_during_conversion_saves_no_asset(monkeypatch):
 uid=await _media_artifact();puts=[]
 class Storage:
  async def get_bytes(self,*a,**kw):
   async with SessionFactory() as other:
    row=await other.get(ArtifactModel,uid);row.artifact_metadata={**row.artifact_metadata,'caption':'changed'};await other.commit()
   return b'source'
  async def put(self,**kw):puts.append(kw);return 's3://should-not-write'
 monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
 monkeypatch.setattr('app.domain.video_derivative.video_derivative',lambda *a:(b'converted',{}))
 async with SessionFactory() as s:
  row=await s.get(ArtifactModel,uid);row.kind='VIDEO';row.mime_type='video/mp4';fp=source_fingerprint(row)
  s.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={},source_fingerprint=fp,origin='UNCHANGED_ORIGINAL',version=1));await s.commit()
 from app.application import platform_copy_media as media
 async with SessionFactory() as s:
  with pytest.raises(ValueError,match='تغير'):await media.prepare_video(s,uid,'instagram',fingerprint=fp,version=1)
 assert not puts

@pytest.mark.asyncio
async def test_conversion_failure_leaves_source_and_selection_intact(monkeypatch):
 uid=await _media_artifact();puts=[]
 class Storage:
  async def get_bytes(self,*a,**kw):return b'source'
  async def put(self,**kw):puts.append(kw)
 monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
 def fail(*args):raise RuntimeError('encoder timeout')
 monkeypatch.setattr('app.domain.video_derivative.video_derivative',fail)
 async with SessionFactory() as s:
  row=await s.get(ArtifactModel,uid);row.kind='VIDEO';row.mime_type='video/mp4';fp=source_fingerprint(row);original=row.storage_uri
  s.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={},source_fingerprint=fp,origin='UNCHANGED_ORIGINAL',version=1));await s.commit()
  from app.application.platform_copy_media import prepare_video
  with pytest.raises(ValueError,match='تعذر'):await prepare_video(s,uid,'instagram',fingerprint=fp,version=1)
 async with SessionFactory() as s:
  copy=await s.get(PlatformCopyModel,(uid,'instagram'));row=await s.get(ArtifactModel,uid)
  assert copy.version==1 and copy.selected_media_id is None and row.storage_uri==original and not puts

@pytest.mark.asyncio
async def test_storage_failure_leaves_no_private_row_or_selection(monkeypatch):
 from app.infrastructure.artifact_storage import ArtifactStorageError
 from app.application.platform_copy_media import prepare_video
 uid=await _media_artifact()
 class Storage:
  async def get_bytes(self,*a,**kw):return b'source'
  async def put(self,**kw):raise ArtifactStorageError('synthetic unavailable')
 monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
 monkeypatch.setattr('app.domain.video_derivative.video_derivative',lambda *a:(b'derivative',{}))
 async with SessionFactory() as s:
  row=await s.get(ArtifactModel,uid);row.kind='VIDEO';row.mime_type='video/mp4';fp=source_fingerprint(row)
  s.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={},source_fingerprint=fp,origin='UNCHANGED_ORIGINAL',version=1));await s.commit()
  with pytest.raises(ArtifactStorageError):await prepare_video(s,uid,'instagram',fingerprint=fp,version=1)
  await s.rollback()
 async with SessionFactory() as s:
  copy=await s.get(PlatformCopyModel,(uid,'instagram'));assert copy.version==1 and copy.selected_media_id is None
  assert not (await s.execute(select(PlatformCopyMediaModel).where(PlatformCopyMediaModel.artifact_id==uid))).scalars().all()

@pytest.mark.asyncio
async def test_concurrent_same_content_reuses_one_private_object(monkeypatch):
 import asyncio
 from app.application.platform_copy_media import prepare_video
 uid=await _media_artifact();puts=[]
 class Storage:
  async def get_bytes(self,*a,**kw):await asyncio.sleep(.01);return b'source'
  async def put(self,*,key,**kw):await asyncio.sleep(.02);puts.append(key);return 's3://synthetic/'+key
 monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
 monkeypatch.setattr('app.domain.video_derivative.video_derivative',lambda *a:(b'derivative',{}))
 async with SessionFactory() as s:
  row=await s.get(ArtifactModel,uid);row.kind='VIDEO';row.mime_type='video/mp4';fp=source_fingerprint(row)
  s.add(PlatformCopyModel(artifact_id=uid,platform='instagram',fields={},source_fingerprint=fp,origin='UNCHANGED_ORIGINAL',version=1));await s.commit()
 async def run():
  async with SessionFactory() as s:return await prepare_video(s,uid,'instagram',fingerprint=fp,version=1)
 a,b=await asyncio.gather(run(),run());assert a['media']['id']==b['media']['id'] and len(puts)==1
