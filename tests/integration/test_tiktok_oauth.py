import json
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import pytest
from sqlalchemy import delete
from app.application import tiktok_oauth as service
from app.infrastructure.database.models import TikTokOAuthFlowModel as Flow,TikTokConnectionModel as Connection,PlatformAppSettingsModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_instagram_oauth import config,browser
SETTINGS=dict(client_key='synthetic-key',client_secret='synthetic-secret',redirect_uri='https://test/api/connections/tiktok/callback',config_reviewed=True)
async def clear():
    async with SessionFactory() as s:
        await s.execute(delete(Flow));await s.execute(delete(Connection));await s.execute(delete(PlatformAppSettingsModel).where(PlatformAppSettingsModel.platform=='tiktok_login'));await s.commit()
async def start(c):
    assert (await c.post(service.BASE+'/settings',json=SETTINGS)).status_code==200
    r=await c.post(service.BASE+'/start');assert r.status_code==200,r.text
    q=parse_qs(urlsplit(r.json()['authorization_url']).query);assert q['scope']==['user.info.basic'] and q['disable_auto_auth']==['1']
    return q['state'][0]
def mock(monkeypatch):
    async def exchange(code,c):return {'open_id':'test-id','access_token':'private-access','refresh_token':'private-refresh','expires_in':7200,'refresh_expires_in':86400,'scope':'user.info.basic','token_type':'Bearer'},{'open_id':'test-id','display_name':'اسم تجريبي'}
    async def identity(t):return {'open_id':t['open_id'],'display_name':'اسم تجريبي'}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',identity)
@pytest.mark.asyncio
async def test_lifecycle_binding_replay_encryption_and_no_execution(config,monkeypatch):
    await clear();mock(monkeypatch)
    async with browser() as c:
        state=await start(c)
        async with browser() as stranger:assert (await stranger.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'})).status_code==400
        callback=await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'})
        assert callback.status_code==303
        assert callback.headers['location']=='/connections#platform-tiktok'
        r=await c.get(service.BASE);assert not r.json()['connection'] and r.json()['pending']['accounts'][0]['open_id']=='test-id';assert 'private-' not in r.text
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'replay'})).status_code==400
        assert (await c.post(service.BASE+'/select',json={'open_id':'wrong'})).status_code==409
        assert (await c.post(service.BASE+'/select',json={'open_id':'test-id'})).status_code==200
        r=await c.get(service.BASE);assert r.json()['connection']['open_id']=='test-id' and not r.json()['execution_authorized'] and 'private-' not in r.text
        async with SessionFactory() as s:
            r=await s.get(Connection,1);assert 'private-' not in r.token_ciphertext;assert json.loads(service.key().decrypt(r.token_ciphertext.encode()))['refresh_token']=='private-refresh'
        assert (await c.post(service.BASE+'/verify')).status_code==200
        assert (await c.post(service.BASE+'/publish')).status_code==404
        assert (await c.post(service.BASE+'/upload')).status_code==404
        assert (await c.post(service.BASE+'/disconnect')).json()['remote_revoked'] is False
        assert (await c.get(service.BASE)).json()['connection'] is None
@pytest.mark.asyncio
async def test_config_expiry_cancel_origin_and_safe_error(config,monkeypatch,caplog):
    await clear();mock(monkeypatch)
    async with browser() as c:
        assert (await c.post(service.BASE+'/start')).status_code==409
        for changes in [{'config_reviewed':False},{'redirect_uri':'https://evil.invalid/api/connections/tiktok/callback'},{'redirect_uri':SETTINGS['redirect_uri']+'?x=1'}]:assert (await c.post(service.BASE+'/settings',json={**SETTINGS,**changes})).status_code==409
        assert (await c.post(service.BASE+'/settings',json=SETTINGS,headers={'Origin':'https://evil.invalid'})).status_code==403
        state=await start(c)
        assert (await c.get(service.BASE+'/callback',params={'state':state,'error':'denied'})).status_code==400
        state=await start(c)
        async with SessionFactory() as s:
            r=await s.get(Flow,service.digest(state));r.expires_at=service.now()-timedelta(seconds=1);await s.commit()
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'})).status_code==400
        state=await start(c)
        async def bad(*a):raise ValueError('private-provider-error')
        monkeypatch.setattr(service,'exchange',bad)
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive'});assert r.status_code==400 and 'private-' not in r.text+caplog.text and 'sensitive' not in caplog.text
@pytest.mark.asyncio
async def test_preserve_existing_on_failed_selection_and_expiry(config,monkeypatch):
    await clear();mock(monkeypatch)
    async with browser() as c:
        state=await start(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});assert (await c.post(service.BASE+'/select',json={'open_id':'test-id'})).status_code==200
        old=(await c.get(service.BASE)).json()['connection'];state=await start(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        async def bad(*a):raise ValueError('private-error')
        monkeypatch.setattr(service,'selected_facts',bad)
        assert (await c.post(service.BASE+'/select',json={'open_id':'test-id'})).status_code==409
        assert (await c.get(service.BASE)).json()['connection']==old
        assert (await c.post(service.BASE+'/verify')).status_code==409
        assert (await c.get(service.BASE)).json()['connection']['last_check_ok'] is False
        async with SessionFactory() as s:
            r=await s.get(Connection,1);r.token_expires_at=service.now()-timedelta(seconds=1);await s.commit()
        assert (await c.post(service.BASE+'/verify')).status_code==409
        assert (await c.get(service.BASE)).json()['connection']['state']=='RECONNECT_REQUIRED'


@pytest.mark.asyncio
async def test_background_cleanup_boundary_preserves_live_flow_and_connection(config, monkeypatch):
    await clear(); mock(monkeypatch)
    async with browser() as c:
        state=await start(c)
        await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        assert (await c.post(service.BASE+'/select',json={'open_id':'test-id'})).status_code==200
        before=(await c.get(service.BASE)).json()['connection']
        state=await start(c)
        await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        fixed=service.now()
        monkeypatch.setattr(service,'now',lambda:fixed)
        async with SessionFactory() as session:
            live=await session.get(Flow,service.digest(state))
            live.expires_at=fixed+timedelta(seconds=1)
            for index,offset in enumerate([-1,0]):
                session.add(Flow(id='expired-'+str(index),session_hash='synthetic',browser_hash='synthetic',config_hash='synthetic',expires_at=fixed+timedelta(seconds=offset),consumed=True,accounts=[],token_ciphertext='encrypted-candidate'))
            await session.commit()
        assert await service.cleanup_expired_flows()==2
        assert await service.cleanup_expired_flows()==0
        assert (await c.get(service.BASE)).json()['pending'] is not None
        assert (await c.get(service.BASE)).json()['connection']==before
        monkeypatch.setattr(service,'now',lambda:fixed+timedelta(seconds=1))
        assert await service.cleanup_expired_flows()==1
        async with SessionFactory() as session:
            assert await session.get(Flow,service.digest(state)) is None
            assert await session.get(Connection,1) is not None


@pytest.mark.asyncio
async def test_cleanup_skips_busy_lifecycle_lock(config):
    async with SessionFactory() as session:
        await service.lock(session)
        assert await service.cleanup_expired_flows()==0
        await session.rollback()
