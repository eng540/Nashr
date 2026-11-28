from datetime import timedelta,datetime,timezone
from uuid import UUID
import pytest
from sqlalchemy import select
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel,FacebookReelJobModel as Facebook,InstagramExecutionModel as Instagram,InstagramDispatchModel as Dispatch,InstagramConnectionModel as Connection
from app.application import facebook_reel_runtime as fb,instagram_publish_decisions as decisions,instagram_unified_execution as execution,instagram_dispatch as dispatch,instagram_runtime as runtime,instagram_oauth as oauth
from tests.integration.test_instagram_oauth import config,browser
from tests.integration.test_instagram_unified_execution_gates import approved
from tests.integration.test_instagram_execution_core import private_storage

@pytest.mark.asyncio
async def test_fb_future_pins_time_no_early_calls_expiry_and_legacy(config,monkeypatch):
    from tests.integration.test_media_scheduling import _media_artifact
    uid=await _media_artifact();facts=dict(artifact_id=str(uid),media_sha256='a'*64,caption='exact',size_bytes=10);binding={'page_id':'123','page_name':'Page'}
    async def pinned(*a):return facts,b'bytes'
    async def bound(*a):return binding
    monkeypatch.setattr(fb,'pinned',pinned);monkeypatch.setattr(fb,'binding',bound)
    due=fb.now()+timedelta(days=2)
    async with SessionFactory() as s:
        j=await fb.stage(s,uid,due_at=due,timezone_name='Asia/Riyadh');job=await s.get(Facebook,UUID(j['id']))
        assert job.snapshot['due_at']==due.isoformat() and job.state=='DRAFT'
        assert (await fb.stage(s,uid,due_at=due,timezone_name='Asia/Riyadh'))['id']==j['id']
        with pytest.raises(ValueError):await fb.approve(s,job,'b'*64,'owner-session:12345678')
        await fb.approve(s,job,j['snapshot_hash'],'owner-session:12345678');assert job.approved_until==due+timedelta(minutes=30)
        def forbidden(*a):raise AssertionError('No early provider or upload')
        monkeypatch.setattr(fb,'provider',forbidden)
        await fb.process_one(s,job)
        with pytest.raises(ValueError,match='موعد'):await fb.valid(s,job)
        monkeypatch.setattr(fb,'now',lambda:due+timedelta(seconds=1));assert await fb.valid(s,job)==b'bytes'
        monkeypatch.setattr(fb,'now',lambda:due+timedelta(minutes=31))
        with pytest.raises(ValueError):await fb.valid(s,job)
        legacy=await fb.stage(s,uid);old=await s.get(Facebook,UUID(legacy['id']));assert 'due_at' not in old.snapshot
        await fb.approve(s,old,legacy['snapshot_hash'],'owner-session:12345678');assert old.approved_until==fb.now()+timedelta(minutes=30)

@pytest.mark.asyncio
@pytest.mark.parametrize('delta,zone',[(timedelta(days=8),'UTC'),(timedelta(seconds=-1),'UTC'),(timedelta(days=1),'Invalid/Zone')])
async def test_bad_times_rejected_without_media(config,monkeypatch,delta,zone):
    from app.application.exact_schedule_time import timing
    with pytest.raises((ValueError,KeyError)):timing(datetime.now(timezone.utc)+delta,zone,now=datetime.now(timezone.utc))

@pytest.mark.asyncio
async def test_future_instagram_refresh_same_pinned_account_only(config,monkeypatch):
    jid,did,due=await approved(monkeypatch);seen=[]
    async with SessionFactory() as s:
        conn=await s.get(Connection,1);conn.last_check_at=oauth.now()-timedelta(hours=2);await s.commit();job=await s.get(Instagram,jid)
        with pytest.raises(ValueError):await execution.validate_binding(s,job)
        async def verify(session):
            seen.append('verify-read-only');conn.last_check_at=oauth.now();await session.commit()
        monkeypatch.setattr(oauth,'verify_saved_connection',verify)
        await execution.refresh_due_binding(s,job);assert seen==['verify-read-only']
        conn.account_id='999';await s.commit()
        with pytest.raises(ValueError):await execution.refresh_due_binding(s,job)
        assert len(seen)==1

@pytest.mark.asyncio
async def test_operation_index_private_paginated_no_secrets(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        await dispatch.schedule(s,jid,did)
        job=await s.get(Instagram,jid)
        artifact=await s.get(ArtifactModel,job.artifact_id)
        artifact.artifact_metadata={**(artifact.artifact_metadata or {}),'caption':'عنوان واضح من التعليق'}
        await s.commit()
    async with browser() as c:
        r=await c.get('/api/platform-operations?limit=1');assert r.status_code==200,r.text
        d=r.json();assert d['total']>=1 and len(d['items'])==1
        assert d['counts']['total']==d['total'] and d['counts']['waiting']>=1
        assert len(d['items'][0]['title'])<=120
        all_rows=(await c.get('/api/platform-operations?limit=100')).json()['items']
        assert next(x for x in all_rows if x['id']==str(jid))['title']=='عنوان واضح من التعليق'
        assert r.headers['cache-control']=='no-store'
        if d['items'][0]['due_at']:assert 'T' in d['items'][0]['due_at']
        assert not any(x in r.text for x in ['evidence_ref','token_hash','private-token','connection_binding','snapshot_hash'])
        assert (await c.get('/api/platform-operations?limit=101')).status_code==422

@pytest.mark.asyncio
async def test_due_runtime_refreshes_before_decision_but_expired_does_not(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        for row in (await s.execute(select(Dispatch))).scalars():row.state='CANCELLED'
        row=await dispatch.schedule(s,jid,did)
    seen=[]
    async def refresh(*a):seen.append('refresh')
    async def validate(*a):seen.append('validate');raise ValueError('stop before provider')
    monkeypatch.setattr(execution,'refresh_due_binding',refresh);monkeypatch.setattr(decisions,'validate',validate)
    monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1))
    await runtime.process_approved();assert seen==['refresh','validate']
    async with SessionFactory() as s:
        r=await s.get(Dispatch,row.id);r.state='PENDING';await s.commit()
    seen.clear();monkeypatch.setattr(decisions,'now',lambda:due+timedelta(minutes=16))
    await runtime.process_approved();assert seen==[]

@pytest.mark.asyncio
async def test_fb_processing_window_expiry_blocks_finish_but_known_result_recovers(monkeypatch):
    from types import SimpleNamespace
    from app.adapters.publishing.facebook_reels import ReelSession
    from dataclasses import asdict
    class S:
        async def commit(self):pass
    due=fb.now()-timedelta(minutes=31);calls=[]
    job=SimpleNamespace(state='PROCESSING',snapshot={'due_at':due.isoformat(),'caption':'exact'},approved_until=due+timedelta(minutes=30),remote_session=asdict(ReelSession('123','456','https://rupload.facebook.com/video-upload/456','a'*64,5)),updated_at=fb.now(),permalink=None,error_code=None)
    async def valid(*a):raise ValueError('expired')
    class Provider:
        async def status(self,*a):calls.append('status');return dict(state='OK',publishing_complete=True,publish_status='published')
        async def _request(self,*a,**k):calls.append('read');return dict(id='456',description='exact',**{'from':{'id':'123'}},permalink_url='https://www.facebook.com/reel/456/')
        async def finish(self,*a,**k):raise AssertionError('No expired finish')
        async def upload(self,*a,**k):raise AssertionError('No reupload')
    async def provider(*a):return Provider()
    monkeypatch.setattr(fb,'provider',provider);monkeypatch.setattr(fb,'valid',valid)
    with pytest.raises(ValueError):await fb.process_one(S(),job)
    assert calls==[]
    job.state='OUTCOME_UNKNOWN';await fb.process_one(S(),job)
    assert job.state=='PUBLISHED' and calls==['status','read']

@pytest.mark.asyncio
async def test_instagram_processing_expiry_blocks_without_provider_or_renewal(config,monkeypatch):
    from app.infrastructure.database.models import InstagramMediaGrantModel as Grant
    from app.application import instagram_media_grants as grants
    jid,did,due=await approved(monkeypatch)
    async with SessionFactory() as s:
        for row in (await s.execute(select(Dispatch))).scalars():row.state='CANCELLED'
        row=await dispatch.schedule(s,jid,did)
        monkeypatch.setattr(decisions,'now',lambda:due+timedelta(seconds=1));grant,token=await grants.mint(s,jid,did)
        row.state='WAITING_MEDIA';await s.commit()
    monkeypatch.setattr(decisions,'now',lambda:due+timedelta(minutes=16))
    def forbidden(*a):raise AssertionError('No expired provider or grant renewal')
    monkeypatch.setattr(execution,'refresh_due_binding',forbidden);monkeypatch.setattr(execution,'verified_provider',forbidden)
    await runtime.process_approved()
    async with SessionFactory() as s:
        row=await s.get(Dispatch,row.id);assert row.state=='WAITING_MEDIA' # Scheduler cannot rewrite exact claim truth on expiry
        with pytest.raises(ValueError):await grants.read(s,token)


@pytest.mark.asyncio
async def test_index_needs_owner():
    import httpx
    from app.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.get('/api/platform-operations')).status_code==401

@pytest.mark.asyncio
async def test_operation_calendar_filters_day_in_requested_zone_and_rejects_invalid_input(config,monkeypatch):
    jid,did,due=await approved(monkeypatch)
    from datetime import datetime,timezone,timedelta
    async with SessionFactory() as s:
        row=await dispatch.schedule(s,jid,did)
        row.due_at=datetime(2030,1,1,22,30,tzinfo=timezone.utc)
        await s.commit()
    async with browser() as c:
        for zone,day,present in [('Asia/Riyadh','2030-01-02',True),('UTC','2030-01-01',True),('Asia/Riyadh','2030-01-01',False)]:
            response=await c.get('/api/platform-operations',params={'date':day,'timezone':zone})
            assert response.status_code==200,response.text
            body=response.json()
            assert body['date']==day and body['timezone']==zone
            assert (str(jid) in [x['id'] for x in body['items']]) is present
            assert response.headers['cache-control']=='no-store'
            assert not any(secret in response.text for secret in ['evidence_ref','connection_binding','snapshot_hash'])
        assert (await c.get('/api/platform-operations?date=2030-02-30&timezone=UTC')).status_code==400
        assert (await c.get('/api/platform-operations?date=2030-01-01&timezone=No/Zone')).status_code==400
        assert (await c.get('/api/platform-operations?date=not-a-day')).status_code==422

@pytest.mark.asyncio
async def test_operation_calendar_half_open_dst_day_filters_all_reel_states_and_paginates(config):
    from tests.integration.test_media_scheduling import _media_artifact
    uid=await _media_artifact();created=[]
    # New York's spring transition is a23-hour local day, not a fixed UTC24hours.
    times=[datetime(2030,3,10,4,59,tzinfo=timezone.utc),datetime(2030,3,10,5,tzinfo=timezone.utc),datetime(2030,3,11,3,59,tzinfo=timezone.utc),datetime(2030,3,11,4,tzinfo=timezone.utc),None]
    async with SessionFactory() as s:
        for index,due in enumerate(times):
            row=Facebook(artifact_id=uid,snapshot={'due_at':due.isoformat() if due else None,'timezone':'UTC','connection':{'page_name':'synthetic'}},snapshot_hash=str(index)*64,state='CANCELLED' if index==2 else 'OUTCOME_UNKNOWN',evidence_ref='trusted-message:synthetic-only-123',created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc))
            s.add(row);await s.flush();created.append(str(row.id))
        await s.commit()
    async with browser() as c:
        first=(await c.get('/api/platform-operations',params={'date':'2030-03-10','timezone':'America/New_York','limit':1})).json()
        second=(await c.get('/api/platform-operations',params={'date':'2030-03-10','timezone':'America/New_York','limit':1,'offset':1})).json()
        assert first['total']==second['total']==2
        assert first['items'][0]['id']==created[1] and second['items'][0]['id']==created[2]
        assert first['items'][0]['state']=='OUTCOME_UNKNOWN' and second['items'][0]['state']=='CANCELLED'
        assert first['counts']['attention']==1 and first['counts']['total']==2

@pytest.mark.asyncio
async def test_operation_filters_intersect_platform_day_state_and_preserve_other_history(config):
    from tests.integration.test_media_scheduling import _media_artifact
    from app.infrastructure.database.models import FacebookExecutionModel as Text
    uid=await _media_artifact();due=datetime(2031,1,1,22,30,tzinfo=timezone.utc)
    async with SessionFactory() as s:
        for kind,state in [('IMAGE','PUBLISHED_AT_LAST_CHECK'),('TEXT','OUTCOME_UNKNOWN'),('TEXT','CANCELLED'),('TEXT','APPROVED')]:
            s.add(Text(artifact_id=uid,page_id='123',source_fingerprint='a'*64,copy_version=1,kind=kind,message='synthetic',total_bytes=0,runtime_snapshot={'timezone':'UTC','connection':{'page_name':'synthetic'}},evidence_ref='trusted-message:synthetic-only-123',due_at=due,state=state))
        await s.commit()
    async with browser() as c:
        for group,platform,expected in [('all','all',4),('published','facebook_photo',1),('attention','facebook_text',1),('waiting','facebook_text',1),('other','facebook_text',1),('published','facebook_text',0),('all','instagram',0)]:
            params={'date':'2031-01-02','timezone':'Asia/Riyadh','state_group':group,'platform':platform,'limit':1}
            r=await c.get('/api/platform-operations',params=params);assert r.status_code==200,r.text
            j=r.json();assert j['total']==j['counts']['total']==expected
            assert j['platform']==platform and j['state_group']==group
            if expected and group!='all':assert j['counts'].get(group,0)==(0 if group=='other' else 1)
            if platform!='all':assert all(i['platform']==platform for i in j['items'])
            assert r.headers['cache-control']=='no-store'
        assert (await c.get('/api/platform-operations?state_group=typo')).status_code==422
        assert (await c.get('/api/platform-operations?platform=tiktok')).status_code==422
        assert (await c.get('/api/platform-operations?date=2031-01-01&timezone=Asia/Riyadh&platform=facebook_text')).json()['total']==0
