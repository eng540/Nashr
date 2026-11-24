from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete,select
from app.main import app
from app.api.auth import issue_token,SESSION_COOKIE
from app.application import instagram_oauth as service
from app.infrastructure.database.models import InstagramOAuthFlowModel as Flow,InstagramConnectionModel as Connection
from app.infrastructure.database.session import SessionFactory

@pytest.fixture
def config(monkeypatch):
    values={'NASHR_AUTH_PASSWORD':'test-owner','NASHR_SESSION_SECRET':'test-session-secret','META_APP_ID':'123456','META_APP_SECRET':'app-secret-test','META_INSTAGRAM_CONFIG_ID':'456789','META_INSTAGRAM_REDIRECT_URI':'https://test/api/connections/instagram/callback','META_INSTAGRAM_CONFIG_REVIEWED':'true','NASHR_CONNECTION_ENCRYPTION_KEY':Fernet.generate_key().decode()}
    for k,v in values.items():monkeypatch.setenv(k,v)
    return values

async def clear():
    async with SessionFactory() as s:
        await s.execute(delete(Flow));await s.execute(delete(Connection));await s.commit()

def browser():
    c=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test',headers={'Origin':'https://test'})
    c.cookies.set(SESSION_COOKIE,issue_token('admin'));return c

async def start(c):
    response=await c.post(service.BASE+'/start');assert response.status_code==200,response.text
    return parse_qs(urlsplit(response.json()['authorization_url']).query)['state'][0]

@pytest.mark.asyncio
async def test_not_configured_never_emits_fake_url_or_network(config,monkeypatch):
    await clear();monkeypatch.delenv('META_APP_ID')
    async with browser() as c:
        r=await c.get(service.BASE);assert not r.json()['configured'];assert r.headers['cache-control']=='no-store'
        r=await c.post(service.BASE+'/start');assert r.status_code==409 and 'authorization_url' not in r.text
    async with SessionFactory() as s:assert not (await s.execute(select(Flow))).scalars().all()

@pytest.mark.asyncio
async def test_state_session_replay_selection_encryption_and_disconnect(config,monkeypatch):
    await clear();calls=[]
    async def exchange(code,c):
        calls.append(code);return 'server-only-token',[{'account_id':'123','username':'chosen'},{'account_id':'456','username':'other'}],['instagram_basic','instagram_content_publish'],service.now()+timedelta(days=3)
    monkeypatch.setattr(service,'exchange',exchange)
    async with browser() as c:
        state=await start(c)
        async with browser() as stranger:
            r=await stranger.get(service.BASE+'/callback',params={'state':state,'code':'sensitive-code'});assert r.status_code==400 and not calls
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'sensitive-code'});assert r.status_code==303 and r.headers['location']=='/connections'
        assert 'sensitive-code' not in r.text and 'server-only-token' not in r.text
        r=await c.get(service.BASE);assert r.json()['pending']['accounts'][0]['username']=='chosen';assert not r.json()['connection'];assert 'server-only-token' not in r.text
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'again'})).status_code==400 and len(calls)==1
        assert (await c.post(service.BASE+'/select',json={'account_id':'999'})).status_code==409
        assert (await c.post(service.BASE+'/select',json={'account_id':'456'})).status_code==200
        r=await c.get(service.BASE);assert r.json()['connection']['username']=='other';assert not r.json()['execution_authorized']
        async with SessionFactory() as s:
            row=await s.get(Connection,1);assert row.token_ciphertext!='server-only-token';assert service.cipher(service.configuration()).decrypt(row.token_ciphertext.encode())==b'server-only-token'
            assert not (await s.execute(select(Flow))).scalars().all()
        assert (await c.post(service.BASE+'/disconnect')).json()['remote_revoked'] is False
        assert (await c.get(service.BASE)).json()['connection'] is None

@pytest.mark.asyncio
async def test_expired_cancelled_cross_origin_and_configuration_change(config,monkeypatch):
    await clear()
    async with browser() as c:
        assert (await c.post(service.BASE+'/start',headers={'Origin':'https://evil.invalid'})).status_code==403
        state=await start(c)
        assert (await c.get(service.BASE+'/callback',params={'state':state,'error':'access_denied','error_description':'untrusted'})).status_code==400
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'reuse'})).status_code==400
        state=await start(c)
        async with SessionFactory() as s:
            f=await s.get(Flow,service.digest(state));f.expires_at=service.now()-timedelta(seconds=1);await s.commit()
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'expired'})).status_code==400
        state=await start(c);monkeypatch.setenv('META_INSTAGRAM_CONFIG_ID','999999')
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'changed'})).status_code==400
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
        assert (await c.post(service.BASE+'/start')).status_code==401

@pytest.mark.asyncio
async def test_exchange_validates_app_scopes_and_fixed_hosts(config,monkeypatch):
    seen=[];fail=False
    def handler(request):
        seen.append(request)
        if request.url.path.endswith('/oauth/access_token'):return httpx.Response(200,json={'access_token':'private-token'})
        if request.url.path.endswith('/debug_token'):return httpx.Response(200,json={'data':{'app_id':'123456','is_valid':True,'scopes':['instagram_basic'] if fail else ['instagram_basic','instagram_content_publish'],'expires_at':int((service.now()+timedelta(days=2)).timestamp())}})
        return httpx.Response(200,json={'data':[{'id':'111','username':'chosen'}]})
    real=httpx.AsyncClient
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    token,accounts,scopes,expiry=await service.exchange('single-use-code',service.configuration())
    assert token=='private-token' and accounts==[{'account_id':'111','username':'chosen'}] and expiry
    assert all(r.url.host=='graph.facebook.com' for r in seen)
    assert seen[-1].headers['authorization']=='Bearer private-token'
    fail=True
    with pytest.raises(ValueError,match='صلاحيات'):await service.exchange('next-code',service.configuration())

@pytest.mark.asyncio
async def test_concurrent_callback_only_exchanges_once_and_disconnect_wins(config,monkeypatch):
    import asyncio
    await clear();started=asyncio.Event();release=asyncio.Event();calls=[]
    async def exchange(code,c):
        calls.append(code);started.set();await release.wait()
        return 'transient-token',[{'account_id':'111','username':'test'}],['instagram_basic','instagram_content_publish'],None
    monkeypatch.setattr(service,'exchange',exchange)
    async with browser() as c:
        state=await start(c)
        first=asyncio.create_task(c.get(service.BASE+'/callback',params={'state':state,'code':'one'}))
        await started.wait()
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'two'})).status_code==400
        assert (await c.post(service.BASE+'/disconnect')).status_code==200
        release.set();assert (await first).status_code==400
        assert len(calls)==1
        result=(await c.get(service.BASE)).json();assert result['pending'] is None and result['connection'] is None

@pytest.mark.asyncio
async def test_configuration_safety_and_session_isolation(config,monkeypatch):
    await clear()
    for key,value in [('META_INSTAGRAM_REDIRECT_URI','http://evil.invalid/callback'),('NASHR_CONNECTION_ENCRYPTION_KEY','invalid'),('META_INSTAGRAM_CONFIG_REVIEWED','false')]:
        monkeypatch.setenv(key,value);assert service.configuration()['missing'];monkeypatch.setenv(key,config[key])
    async with browser() as c:
        state=await start(c)
        c.cookies.set(SESSION_COOKIE,issue_token('different-owner'))
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'wrong-session'})).status_code==400
    monkeypatch.delenv('NASHR_AUTH_PASSWORD')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test',headers={'Origin':'https://test'}) as c:
        assert (await c.post(service.BASE+'/start')).status_code==401
