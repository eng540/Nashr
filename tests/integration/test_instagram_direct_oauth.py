from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import pytest
from sqlalchemy import delete,select
from app.application import instagram_direct_oauth as service
from app.infrastructure.database.models import InstagramDirectOAuthFlowModel as Flow,InstagramDirectConnectionModel as Connection,PlatformAppSettingsModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_instagram_oauth import config,browser
SETTINGS=dict(app_id='123456',app_secret='synthetic-secret',redirect_uri='https://test/api/connections/instagram-direct/callback',direct_login_reviewed=True)

async def clear():
    async with SessionFactory() as s:
        await s.execute(delete(Flow));await s.execute(delete(Connection));await s.execute(delete(PlatformAppSettingsModel).where(PlatformAppSettingsModel.platform=='instagram_direct'));await s.commit()

async def start(c):
    r=await c.post(service.BASE+'/settings',json=SETTINGS);assert r.status_code==200,r.text
    r=await c.post(service.BASE+'/start');assert r.status_code==200,r.text
    url=urlsplit(r.json()['authorization_url']);q=parse_qs(url.query)
    assert url.hostname=='www.instagram.com' and set(q['scope'][0].split(','))==service.SCOPES
    assert q['enable_fb_login']==['false'] and 'config_id' not in q
    return q['state'][0]

@pytest.mark.asyncio
async def test_full_lifecycle_preserves_other_modes(config,monkeypatch):
    await clear();calls=[]
    from app.application import instagram_page_oauth as page,instagram_oauth as unified
    async with SessionFactory() as s:before=[(await s.get(PlatformAppSettingsModel,n)).ciphertext if await s.get(PlatformAppSettingsModel,n) else None for n in ['instagram_page','instagram']]
    async def exchange(code,c):
        calls.append(code);return 'private-token',dict(account_id='111',username='creator'),sorted(service.SCOPES),service.now()+timedelta(days=3)
    async def facts(c,e):return e['account']
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',facts)
    async with browser() as c:
        state=await start(c)
        async with browser() as stranger:assert (await stranger.get(service.BASE+'/callback',params={'state':state,'code':'x'})).status_code==400
        assert not calls
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'private-code'});assert r.status_code==303
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'again'})).status_code==400 and len(calls)==1
        r=await c.get(service.BASE);assert r.json()['pending']['accounts']==[dict(account_id='111',username='creator')];assert 'private' not in r.text
        assert (await c.post(service.BASE+'/select',json={'account_id':'999'})).status_code==409
        assert (await c.post(service.BASE+'/select',json={'account_id':'111'})).status_code==200
        r=await c.get(service.BASE);assert r.json()['connection']['token_type']=='INSTAGRAM_USER' and not r.json()['execution_authorized']
        async with SessionFactory() as s:
            row=await s.get(Connection,1);assert 'private' not in row.token_ciphertext
        assert (await c.post(service.BASE+'/state',json={'enabled':False})).status_code==200
        assert (await c.post(service.BASE+'/verify')).status_code==200
        assert (await c.get(service.BASE)).json()['connection']['state']=='DISABLED'
        assert (await c.post(service.BASE+'/state',json={'enabled':True})).status_code==200
        assert (await c.post(service.BASE+'/disconnect')).json()['remote_revoked'] is False
        assert (await c.get(service.BASE)).json()['connection'] is None
    async with SessionFactory() as s:assert before==[(await s.get(PlatformAppSettingsModel,n)).ciphertext if await s.get(PlatformAppSettingsModel,n) else None for n in ['instagram_page','instagram']]

@pytest.mark.asyncio
async def test_configuration_auth_origin_and_no_fallback(config):
    await clear()
    async with browser() as c:
        assert (await c.post(service.BASE+'/start')).status_code==409
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'direct_login_reviewed':False})).status_code==409
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'direct_login_reviewed':'yes'})).status_code==422
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'redirect_uri':'https://evil.invalid/api/connections/instagram-direct/callback'})).status_code==409
        assert (await c.post(service.BASE+'/settings',json=SETTINGS,headers={'Origin':'https://evil.invalid'})).status_code==403
        r=await c.post(service.BASE+'/settings',json=SETTINGS);assert r.status_code==200 and 'synthetic-secret' not in r.text
        r=await c.get(service.BASE);assert 'synthetic-secret' not in r.text

@pytest.mark.asyncio
async def test_config_change_invalidates_callback(config,monkeypatch):
    await clear();calls=[]
    async def exchange(code,c):calls.append(code);raise AssertionError()
    monkeypatch.setattr(service,'exchange',exchange)
    async with browser() as c:
        state=await start(c)
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'app_id':'777777'})).status_code==200
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'private-code'})).status_code==400
        assert not calls
