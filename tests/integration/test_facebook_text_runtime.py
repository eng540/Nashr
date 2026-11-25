from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select,delete
from app.application import facebook_text_runtime as r
from app.infrastructure.database.models import FacebookExecutionModel as Job,PlatformCopyModel,ArtifactModel
from app.infrastructure.database.session import SessionFactory
from app.adapters.publishing.facebook import FacebookResult,FacebookProviderError,FacebookPagePublisher
from tests.integration.test_facebook_execution import seed
from tests.integration.test_instagram_oauth import config,browser

@pytest.fixture
def bound(monkeypatch):
    async def binding(s):return dict(page_id='123',page_name='صفحة تجريبية',config_hash='x',connected_at='x',token_hash='x')
    monkeypatch.setattr(r.reels,'binding',binding)

async def staged(s,due=False):
    uid,_=await seed()
    d=await r.stage(s,uid,**(dict(due_at=r.now()+timedelta(hours=1),timezone_name='Asia/Riyadh') if due else {}))
    return uid,await s.get(Job,UUID(d['id']))

class Provider:
    page_id='123'
    def __init__(self):self.calls=[]
    def post_identity(self,value):return FacebookPagePublisher.post_identity(self,value)
    async def publish_text(self,**kw):
        self.calls.append('POST');assert kw['message']=='نص كامل غير مختصر';return FacebookResult('POST_ID_KNOWN','123_456')
    async def verify_post(self,post_id,**kw):
        self.calls.append('GET');return FacebookResult('PUBLISHED_AT_LAST_CHECK',post_id,permalink='https://www.facebook.com/123/posts/456')

def mockprovider(monkeypatch,p):
    async def provider(*a):p.calls.append('binding');return p
    monkeypatch.setattr(r,'provider',provider)

@pytest.mark.asyncio
async def test_exact_stage_approval_dedup_once_known_readback(bound,monkeypatch):
    p=Provider();mockprovider(monkeypatch,p)
    async with SessionFactory() as s:
        uid,j=await staged(s)
        assert j.state=='DRAFT' and not j.evidence_ref
        assert (await r.stage(s,uid))['id']==str(j.id)
        await r.process_one(s,j) # unapproved draft is a no-op
        assert p.calls==[]
        with pytest.raises(ValueError):await r.approve(s,j,'a'*64,'owner-session:12345678')
        await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
        await r.process_one(s,j);assert j.state=='PUBLISHED_AT_LAST_CHECK' and p.calls==['binding','POST','GET']
        await r.process_one(s,j);assert p.calls==['binding','POST','GET','binding','GET']
        with pytest.raises(ValueError):await r.cancel(s,j)

@pytest.mark.asyncio
async def test_future_has_no_remote_reads_expiry_and_copy_fence(bound,monkeypatch):
    p=Provider();mockprovider(monkeypatch,p)
    async with SessionFactory() as s:
        uid,j=await staged(s,True);await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
        await r.process_one(s,j);assert p.calls==[]
        j.due_at=r.now()-timedelta(hours=1);j.approved_until=r.now()-timedelta(seconds=1);await s.commit()
        with pytest.raises(ValueError):await r.process_one(s,j)
        assert p.calls==[]
        uid,j=await staged(s);await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
        c=await s.get(PlatformCopyModel,(uid,'facebook'));c.fields={**c.fields,'description':'changed'};await s.commit()
        with pytest.raises(ValueError):await r.process_one(s,j)
        assert p.calls==[]

@pytest.mark.asyncio
async def test_unknown_does_not_repost_known_recovery_ignores_content_expiry(bound,monkeypatch):
    class Lost(Provider):
        async def publish_text(self,**kw):self.calls.append('POST');raise FacebookProviderError('LOST',outcome_unknown=True)
    p=Lost();mockprovider(monkeypatch,p)
    async with SessionFactory() as s:
        uid,j=await staged(s);await r.approve(s,j,j.runtime_hash,'owner-session:12345678');await r.process_one(s,j)
        assert j.state=='OUTCOME_UNKNOWN' and not j.post_id
        await r.process_one(s,j);assert p.calls==['binding','POST']
        j.post_id='123_456';j.approved_until=r.now()-timedelta(days=1)
        a=await s.get(ArtifactModel,uid);a.review_status='DRAFT';await s.commit()
        await r.process_one(s,j);assert j.state=='PUBLISHED_AT_LAST_CHECK' and p.calls[-2:]==['binding','GET']

@pytest.mark.asyncio
async def test_legacy_and_cancel_and_changed_binding(bound,monkeypatch):
    async with SessionFactory() as s:
        uid,legacy=await seed();j=await s.get(Job,legacy)
        with pytest.raises(ValueError):await r.validate(s,j)
        uid,j=await staged(s,True);await r.approve(s,j,j.runtime_hash,'owner-session:12345678');await r.cancel(s,j)
        assert j.state=='CANCELLED'
        with pytest.raises(ValueError):await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
        uid,j=await staged(s)
        async def changed(s):return dict(page_id='999')
        monkeypatch.setattr(r.reels,'binding',changed)
        with pytest.raises(ValueError):await r.approve(s,j,j.runtime_hash,'owner-session:12345678')

@pytest.mark.asyncio
async def test_routes_explicit_approval_origin_and_operation_index(config,bound):
    uid,_=await seed()
    async with browser() as c:
        path='/api/connections/facebook/text-posts'
        d=(await c.post(path+'/materials/'+str(uid)+'/preview',json={})).json()
        body=dict(snapshot_hash=d['snapshot_hash'],exact_words_approved=True,public_page_approved=True,rights_confirmed=False)
        assert (await c.post(path+'/'+d['id']+'/approve',json=body)).status_code==409
        assert (await c.post(path+'/'+d['id']+'/approve',json={**body,'rights_confirmed':'yes'})).status_code==422
        assert (await c.post(path+'/'+d['id']+'/approve',json=body,headers={'Origin':'https://evil.invalid'})).status_code==403
        assert (await c.post(path+'/'+d['id']+'/approve',json={**body,'rights_confirmed':True})).status_code==200
        rows=(await c.get('/api/platform-operations?limit=100')).json()['items']
        found=next(x for x in rows if x['id']==d['id']);assert found['platform']=='facebook_text' and 'snapshot' not in found and not found['permalink']
        assert (await c.post(path+'/'+d['id']+'/cancel')).json()['state']=='CANCELLED'

@pytest.mark.asyncio
async def test_reject_media_and_extra_fields(bound):
    uid,_=await seed('IMAGE')
    async with SessionFactory() as s:
        with pytest.raises(ValueError):await r.stage(s,uid)
    uid,_=await seed()
    async with SessionFactory() as s:
        c=await s.get(PlatformCopyModel,(uid,'facebook'));c.fields={**c.fields,'title':'must not discard'};await s.commit()
        with pytest.raises(ValueError):await r.stage(s,uid)

@pytest.mark.asyncio
async def test_snapshot_columns_drift_and_post_read_expiry(bound,monkeypatch):
    p=Provider();mockprovider(monkeypatch,p)
    async with SessionFactory() as s:
        for attr,value in [('message','drift'),('page_id','999'),('copy_version',99),('due_at',r.now()),('total_bytes',1)]:
            uid,j=await staged(s);await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
            setattr(j,attr,value);await s.commit()
            with pytest.raises(ValueError):await r.process_one(s,j)
        assert p.calls==[]
        uid,j=await staged(s);await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
        async def expire(*args):
            j.approved_until=r.now()-timedelta(seconds=1);await s.commit();return p
        monkeypatch.setattr(r,'provider',expire)
        with pytest.raises(ValueError):await r.process_one(s,j)
        assert p.calls==[]

@pytest.mark.asyncio
async def test_readback_failure_keeps_known_id_and_unknown_blocks_new_time(bound,monkeypatch):
    class Broken(Provider):
        async def verify_post(self,*a,**kw):self.calls.append('GET');raise FacebookProviderError('READBACK_OFFLINE')
    p=Broken();mockprovider(monkeypatch,p)
    async with SessionFactory() as s:
        uid,j=await staged(s);await r.approve(s,j,j.runtime_hash,'owner-session:12345678')
        with pytest.raises(FacebookProviderError):await r.process_one(s,j)
        assert j.post_id=='123_456' and j.state=='POST_ID_KNOWN'
        with pytest.raises(FacebookProviderError):await r.process_one(s,j)
        assert p.calls.count('POST')==1
        j.post_id=None;j.state='OUTCOME_UNKNOWN';await s.commit()
        with pytest.raises(ValueError):await r.stage(s,uid,due_at=r.now()+timedelta(hours=1),timezone_name='Asia/Riyadh')

@pytest.mark.asyncio
async def test_scanner_recovers_interruption_and_excludes_legacy(bound,monkeypatch):
    p=Provider();mockprovider(monkeypatch,p)
    async with SessionFactory() as s:
        # Isolate active runtime fixtures from other tests, all synthetic.
        await s.execute(delete(Job).where(Job.runtime_snapshot.is_not(None)));await s.commit()
        uid,legacy=await seed();old=await s.get(Job,legacy);old.state='APPROVED'
        uid,j=await staged(s);j.state='SENDING';await s.commit();jid=j.id
    await r.process_approved()
    async with SessionFactory() as s:
        j=await s.get(Job,jid);assert j.state=='OUTCOME_UNKNOWN' and j.error_code=='FACEBOOK_TEXT_INTERRUPTED'
        assert (await s.get(Job,legacy)).state=='APPROVED'
    assert p.calls==[]
