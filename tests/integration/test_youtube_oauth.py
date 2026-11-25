import json
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import pytest
from sqlalchemy import delete
from app.application import youtube_oauth as service
from app.adapters.publishing.youtube_login import SCOPE
from app.infrastructure.database.models import YouTubeOAuthFlowModel as Flow,YouTubeConnectionModel as Connection,PlatformAppSettingsModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_instagram_oauth import config,browser
CID='UC'+'a'*22
OTHER='UC'+'b'*22
SETTINGS=dict(oauth_status='TESTING',client_id='synthetic.apps.googleusercontent.com',client_secret='synthetic-secret',redirect_uri='https://test/api/connections/youtube/callback',config_reviewed=True)
async def clear():
    async with SessionFactory() as s:
        await s.execute(delete(Flow));await s.execute(delete(Connection));await s.execute(delete(PlatformAppSettingsModel).where(PlatformAppSettingsModel.platform=='youtube_readonly'));await s.commit()
async def start(c):
    assert (await c.post(service.BASE+'/settings',json=SETTINGS)).status_code==200
    r=await c.post(service.BASE+'/start');assert r.status_code==200,r.text
    q=parse_qs(urlsplit(r.json()['authorization_url']).query)
    assert q['scope']==[SCOPE] and q['access_type']==['offline'] and q['include_granted_scopes']==['false']
    assert 'select_account' in q['prompt'][0]
    return q['state'][0]
def mock(monkeypatch):
    async def exchange(code,c):return {'access_token':'private-access','refresh_token':'private-refresh','expires_in':3600,'refresh_expires_in':604800,'scope':SCOPE,'token_type':'Bearer'},[{'channel_id':CID,'title':'قناة تجريبية'}]
    async def facts(t):return [{'channel_id':CID,'title':'قناة تجريبية'}]
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',facts)
async def connect(c):
    state=await start(c)
    assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'})).status_code==303
    assert (await c.post(service.BASE+'/select',json={'channel_id':CID})).status_code==200

@pytest.mark.asyncio
async def test_lifecycle_encryption_replay_and_no_upload(config,monkeypatch):
    await clear();mock(monkeypatch)
    async with browser() as c:
        state=await start(c)
        async with browser() as stranger:assert (await stranger.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'})).status_code==400
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'})).status_code==303
        r=await c.get(service.BASE);assert r.json()['pending']['accounts'][0]['channel_id']==CID and r.json()['connection'] is None and 'private-' not in r.text
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'replay'})).status_code==400
        assert (await c.post(service.BASE+'/select',json={'channel_id':OTHER})).status_code==409
        assert (await c.post(service.BASE+'/select',json={'channel_id':CID})).status_code==200
        r=await c.get(service.BASE);assert r.json()['connection']['channel_id']==CID and not r.json()['execution_authorized'] and 'private-' not in r.text
        async with SessionFactory() as s:
            r=await s.get(Connection,1);assert 'private-' not in r.token_ciphertext
            assert json.loads(service.key().decrypt(r.token_ciphertext.encode()))['refresh_token']=='private-refresh'
        assert (await c.post(service.BASE+'/verify')).status_code==200
        for path in ['/upload','/publish','/schedule']:assert (await c.post(service.BASE+path)).status_code==404
        assert (await c.post(service.BASE+'/disconnect')).json()['remote_revoked'] is False
        assert (await c.get(service.BASE)).json()['connection'] is None

@pytest.mark.asyncio
async def test_config_csrf_expiry_cancellation_secret_safety(config,monkeypatch,caplog):
    await clear();mock(monkeypatch)
    async with browser() as c:
        assert (await c.post(service.BASE+'/start')).status_code==409
        for change in [{'config_reviewed':False},{'redirect_uri':'https://evil.invalid/api/connections/youtube/callback'},{'redirect_uri':SETTINGS['redirect_uri']+'?x=1'}]:assert (await c.post(service.BASE+'/settings',json={**SETTINGS,**change})).status_code==409
        assert (await c.post(service.BASE+'/settings',json=SETTINGS,headers={'Origin':'https://evil.invalid'})).status_code==403
        state=await start(c);assert (await c.get(service.BASE+'/callback',params={'state':state,'error':'denied'})).status_code==400
        state=await start(c)
        async with SessionFactory() as s:
            r=await s.get(Flow,service.digest(state));r.expires_at=service.now()-timedelta(seconds=1);await s.commit()
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'})).status_code==400
        state=await start(c)
        async def fail(*a):raise ValueError('private-provider-error')
        monkeypatch.setattr(service,'exchange',fail)
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'});assert r.status_code==400 and 'private-' not in r.text+caplog.text and 'sensitive' not in caplog.text

@pytest.mark.asyncio
async def test_refresh_rotation_same_channel_no_status_network(config,monkeypatch):
    await clear();mock(monkeypatch);calls=[]
    async with browser() as c:
        await connect(c)
        async with SessionFactory() as s:
            r=await s.get(Connection,1);t=json.loads(service.key().decrypt(r.token_ciphertext.encode()));t['access_expires_at']=(service.now()-timedelta(seconds=1)).isoformat();r.token_ciphertext=service.key().encrypt(json.dumps(t).encode()).decode();r.token_expires_at=service.now()-timedelta(seconds=1);await s.commit()
        async def renew(t,c):
            calls.append('refresh');return {**t,'access_token':'private-new','refresh_token':'rotated','access_expires_at':(service.now()+timedelta(hours=1)).isoformat()}
        monkeypatch.setattr(service,'renewed',renew)
        assert (await c.get(service.BASE)).status_code==200 and calls==[]
        assert (await c.post(service.BASE+'/verify')).status_code==200 and calls==['refresh']
        async with SessionFactory() as s:
            r=await s.get(Connection,1);assert json.loads(service.key().decrypt(r.token_ciphertext.encode()))['refresh_token']=='rotated'
        async def changed(t):return [{'channel_id':OTHER,'title':'wrong'}]
        monkeypatch.setattr(service,'selected_facts',changed)
        assert (await c.post(service.BASE+'/verify')).status_code==409
        r=(await c.get(service.BASE)).json()['connection'];assert r['channel_id']==CID and not r['last_check_ok']

@pytest.mark.asyncio
async def test_refresh_expiry_and_failed_replacement_preserve_connection(config,monkeypatch):
    await clear();mock(monkeypatch)
    async with browser() as c:
        await connect(c);old=(await c.get(service.BASE)).json()['connection']
        state=await start(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        async def fail(*a):raise ValueError('revoked')
        monkeypatch.setattr(service,'selected_facts',fail)
        assert (await c.post(service.BASE+'/select',json={'channel_id':CID})).status_code==409
        assert (await c.get(service.BASE)).json()['connection']==old
        async with SessionFactory() as s:
            r=await s.get(Connection,1);t=json.loads(service.key().decrypt(r.token_ciphertext.encode()));t['access_expires_at']=(service.now()-timedelta(seconds=1)).isoformat();t['refresh_expires_at']=(service.now()-timedelta(seconds=1)).isoformat();r.token_ciphertext=service.key().encrypt(json.dumps(t).encode()).decode();await s.commit()
        assert (await c.post(service.BASE+'/verify')).status_code==409
        assert (await c.get(service.BASE)).json()['connection']['state']=='RECONNECT_REQUIRED'

@pytest.mark.asyncio
async def test_cleanup_and_anonymous(config,monkeypatch):
    await clear();mock(monkeypatch)
    async with browser() as c:
        await connect(c);state=await start(c)
        async with SessionFactory() as s:
            f=await s.get(Flow,service.digest(state));f.expires_at=service.now()-timedelta(seconds=1);await s.commit()
        assert await service.cleanup_expired_flows()==1
        assert (await c.get(service.BASE)).json()['connection'] is not None
    import httpx
    from app.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.get(service.BASE)).status_code==401


def test_testing_expiry_cap_does_not_slide_on_refresh():
    initial=service.stamp({'expires_in':3600,'refresh_expires_in':None},testing=True)
    assert timedelta(days=6, hours=23)<__import__('datetime').datetime.fromisoformat(initial['refresh_expires_at'])-service.now()<=timedelta(days=7)
    renewed=service.stamp({'expires_in':3600,'refresh_expires_in':None},initial,testing=True)
    assert renewed['refresh_expires_at']==initial['refresh_expires_at']
