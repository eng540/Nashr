import io,hashlib
from datetime import timedelta
from uuid import UUID
from PIL import Image
import pytest
from app.application import facebook_text_runtime as r
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import FacebookExecutionModel as Job,ArtifactModel,PlatformCopyModel
from tests.integration.test_facebook_execution import seed
from tests.integration.test_facebook_text_runtime import bound,Provider,mockprovider
from tests.integration.test_instagram_oauth import config,browser

@pytest.fixture
def imagebytes(monkeypatch):
    b=io.BytesIO();Image.new('RGB',(640,800),'blue').save(b,format='PNG');store={'data':b.getvalue()}
    class Storage:
        async def get_bytes(self,*a,**kw):return store['data']
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    return store

class Photo(Provider):
    async def publish_photo(self,**kw):
        self.calls.append('PHOTO');assert hashlib.sha256(kw['content']).hexdigest()==kw['sha256'];return __import__('app.adapters.publishing.facebook',fromlist=['FacebookResult']).FacebookResult('POST_ID_KNOWN','123_456','456')

@pytest.mark.asyncio
async def test_photo_once_exact_bytes_future_and_known_recovery(bound,imagebytes,monkeypatch):
    p=Photo();mockprovider(monkeypatch,p);uid,_=await seed('IMAGE')
    async with SessionFactory() as s:
        d=await r.stage(s,uid,kind='IMAGE',due_at=r.now()+timedelta(hours=1),timezone_name='Asia/Riyadh');j=await s.get(Job,UUID(d['id']))
        assert j.total_bytes==len(imagebytes['data']) and j.media_sha256==hashlib.sha256(imagebytes['data']).hexdigest()
        await r.approve(s,j,j.runtime_hash,'owner-session:12345678');await r.process_one(s,j);assert p.calls==[]
        import datetime
        old=r.now();monkeypatch.setattr(r,'now',lambda:old+timedelta(hours=1,seconds=1))
        await r.process_one(s,j);assert j.state=='PUBLISHED_AT_LAST_CHECK' and p.calls==['binding','PHOTO','GET']
        await r.process_one(s,j);assert p.calls.count('PHOTO')==1

@pytest.mark.asyncio
async def test_changed_photo_bytes_blocks_before_provider(bound,imagebytes,monkeypatch):
    p=Photo();mockprovider(monkeypatch,p);uid,_=await seed('IMAGE')
    async with SessionFactory() as s:
        d=await r.stage(s,uid,kind='IMAGE');j=await s.get(Job,UUID(d['id']));await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
        b=io.BytesIO();Image.new('RGB',(640,800),'red').save(b,format='PNG');imagebytes['data']=b.getvalue()
        with pytest.raises(ValueError):await r.process_one(s,j)
        assert p.calls==[] and j.state=='APPROVED'

@pytest.mark.asyncio
async def test_photo_route_five_consent_fields_and_text_route_cannot_approve(bound,imagebytes,config):
    uid,_=await seed('IMAGE')
    async with browser() as c:
        base='/api/connections/facebook/photo-posts';d=(await c.post(base+'/materials/'+str(uid)+'/preview',json={})).json()
        body=dict(snapshot_hash=d['snapshot_hash'],exact_words_approved=True,public_page_approved=True,rights_confirmed=True,exact_image_approved=True,private_bytes_disclosure_approved=False)
        assert (await c.post(base+'/'+d['id']+'/approve',json=body)).status_code==409
        assert (await c.post('/api/connections/facebook/text-posts/'+d['id']+'/approve',json={k:v for k,v in body.items() if k not in {'exact_image_approved','private_bytes_disclosure_approved'}})).status_code==404
        assert (await c.post(base+'/'+d['id']+'/approve',json={**body,'private_bytes_disclosure_approved':True})).status_code==200
        rows=(await c.get('/api/platform-operations?limit=100')).json()['items'];assert next(x for x in rows if x['id']==d['id'])['platform']=='facebook_photo'
        assert (await c.post(base+'/'+d['id']+'/cancel')).json()['state']=='CANCELLED'
