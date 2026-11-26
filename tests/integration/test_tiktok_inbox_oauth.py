"""Synthetic permission-only Sandbox flow. Never transfers real content."""
import json
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import pytest
from sqlalchemy import delete
from app.application import tiktok_inbox_oauth as service
from app.infrastructure.database.models import TikTokInboxOAuthFlowModel as Flow,TikTokInboxConnectionModel as Connection,TikTokConnectionModel as Basic
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_instagram_oauth import config,browser
from tests.integration.test_tiktok_oauth import SETTINGS,clear as clear_basic

async def clear():
    async with SessionFactory() as s:
        await s.execute(delete(Flow));await s.execute(delete(Connection));await s.commit()
    await clear_basic()

async def setup(c,monkeypatch):
    await clear();monkeypatch.setenv('NASHR_TIKTOK_INBOX_SANDBOX_REVIEWED','true')
    assert (await c.post('/api/connections/tiktok/settings',json=SETTINGS)).status_code==200
    async with SessionFactory() as s:
        s.add(Basic(id=1,open_id='test-id',display_name='basic-name',token_ciphertext='unchanged-basic',config_hash='unchanged-hash',scopes=['user.info.basic'],token_expires_at=service.now()+timedelta(hours=1),connected_at=service.now(),enabled=True));await s.commit()
    async def exchange(code,c):return dict(open_id='test-id',access_token='private-access',refresh_token='private-refresh',expires_in=7200,refresh_expires_in=86400,scope='user.info.basic,video.upload',token_type='Bearer'),dict(open_id='test-id',display_name='sandbox-name')
    async def identity(t):return dict(open_id=t['open_id'],display_name='sandbox-name')
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',identity)

async def start(c):
    r=await c.post(service.BASE+'/start',json={'reviewed':True});assert r.status_code==200,r.text
    q=parse_qs(urlsplit(r.json()['authorization_url']).query)
    assert q['scope']==['user.info.basic,video.upload'] and q['redirect_uri']==['https://test/api/connections/tiktok-inbox/callback']
    return q['state'][0]

@pytest.mark.asyncio
async def test_disabled_default_and_explicit_review(config,monkeypatch):
    async with browser() as c:
        await setup(c,monkeypatch);monkeypatch.delenv('NASHR_TIKTOK_INBOX_SANDBOX_REVIEWED')
        assert not (await c.get(service.BASE)).json()['configured']
        assert (await c.post(service.BASE+'/start',json={'reviewed':True})).status_code==409
        monkeypatch.setenv('NASHR_TIKTOK_INBOX_SANDBOX_REVIEWED','true')
        for body in [{},{'reviewed':False},{'reviewed':'true'},{'reviewed':True,'extra':True}]:
            assert (await c.post(service.BASE+'/start',json=body)).status_code in (409,422)
        assert (await c.post(service.BASE+'/start',json={'reviewed':True},headers={'Origin':'https://evil.invalid'})).status_code==403

@pytest.mark.asyncio
async def test_independent_lifecycle_no_execution_and_basic_unchanged(config,monkeypatch,caplog):
    async with browser() as c:
        await setup(c,monkeypatch);state=await start(c)
        async with browser() as stranger:assert (await stranger.get(service.BASE+'/callback',params={'state':state,'code':'secret-code'})).status_code==400
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'secret-code'});assert r.status_code==303 and r.headers['location']=='/connections#platform-tiktok-inbox'
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'replay'})).status_code==400
        r=await c.get(service.BASE);assert r.json()['pending'] and r.json()['connection'] is None and 'private-' not in r.text
        assert (await c.post(service.BASE+'/select',json={'open_id':'wrong'})).status_code==409
        assert (await c.post(service.BASE+'/select',json={'open_id':'test-id'})).status_code==200
        r=await c.get(service.BASE);d=r.json();assert d['connection']['scopes']==['user.info.basic','video.upload']
        assert not d['execution_authorized'] and not d['transfer_available'] and not d['public_posting_available']
        assert 'private-' not in r.text+caplog.text and 'secret-code' not in caplog.text
        for action in ['upload','publish','refresh']:assert (await c.post(service.BASE+'/'+action)).status_code==404
        async with SessionFactory() as s:
            basic=await s.get(Basic,1);assert basic.token_ciphertext=='unchanged-basic' and basic.config_hash=='unchanged-hash'
            row=await s.get(Connection,1);assert 'private-' not in row.token_ciphertext
            assert json.loads(service.key().decrypt(row.token_ciphertext.encode()))['refresh_token']=='private-refresh'
        assert (await c.post(service.BASE+'/disconnect')).status_code==200
        async with SessionFactory() as s:assert (await s.get(Basic,1)).token_ciphertext=='unchanged-basic'

@pytest.mark.asyncio
async def test_different_identity_fails_preserves_basic_and_draft(config,monkeypatch):
    async with browser() as c:
        await setup(c,monkeypatch);state=await start(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        async with SessionFactory() as s:
            row=await s.get(Basic,1);row.open_id='other-id';await s.commit()
        assert (await c.post(service.BASE+'/select',json={'open_id':'test-id'})).status_code==409
        assert (await c.get(service.BASE)).json()['connection'] is None
        async with SessionFactory() as s:assert (await s.get(Basic,1)).token_ciphertext=='unchanged-basic'

@pytest.mark.asyncio
async def test_expiry_cancel_and_cleanup(config,monkeypatch):
    async with browser() as c:
        await setup(c,monkeypatch);state=await start(c)
        assert (await c.get(service.BASE+'/callback',params={'state':state,'error':'denied'})).status_code==400
        state=await start(c)
        async with SessionFactory() as s:
            f=await s.get(Flow,service.digest(state));f.expires_at=service.now()-timedelta(seconds=1);await s.commit()
        assert await service.cleanup_expired_flows()==1
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'expired'})).status_code==400

@pytest.mark.asyncio
async def test_callback_missing_encryption_key_safe_failure(config,monkeypatch,caplog):
    async with browser() as c:
        await setup(c,monkeypatch);state=await start(c)
        monkeypatch.delenv('NASHR_CONNECTION_ENCRYPTION_KEY')
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'private-code'})
        assert r.status_code==400 and 'حماية الأسرار' in r.text
        assert 'private-code' not in r.text+caplog.text
        async with SessionFactory() as s:assert (await s.get(Basic,1)).token_ciphertext=='unchanged-basic'

@pytest.mark.asyncio
async def test_saved_consent_requires_same_enabled_basic_identity(config,monkeypatch):
    async with browser() as c:
        await setup(c,monkeypatch);state=await start(c)
        await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        assert (await c.post(service.BASE+'/select',json={'open_id':'test-id'})).status_code==200
        async with SessionFactory() as s:
            row=await s.get(Basic,1);row.open_id='changed-id';await s.commit()
        assert (await c.get(service.BASE)).json()['connection']['state']=='RECONNECT_REQUIRED'
        assert (await c.post(service.BASE+'/verify')).status_code==409
        async with SessionFactory() as s:
            row=await s.get(Basic,1);row.open_id='test-id';row.enabled=False;await s.commit()
        assert (await c.get(service.BASE)).json()['connection']['state']=='RECONNECT_REQUIRED'
        async with SessionFactory() as s:
            await s.execute(delete(Basic));await s.commit()
        assert (await c.get(service.BASE)).json()['connection']['state']=='RECONNECT_REQUIRED'
        assert (await c.post(service.BASE+'/disconnect')).status_code==200
