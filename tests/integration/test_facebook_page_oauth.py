from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import httpx,pytest
from sqlalchemy import delete,select
from app.application import facebook_page_oauth as service
from app.adapters.publishing.facebook_page_login import FacebookPageCandidate
from app.infrastructure.database.models import FacebookPageOAuthFlowModel as Flow,FacebookPageConnectionModel as Connection,PlatformAppSettingsModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_instagram_oauth import config,browser

SETTINGS=dict(app_id='123456',app_secret='synthetic-secret',config_id='456789',redirect_uri='https://test/api/connections/facebook/callback',config_reviewed=True,token_mode='SYSTEM_USER')

async def clear():
    async with SessionFactory() as s:
        await s.execute(delete(Flow));await s.execute(delete(Connection));await s.execute(delete(PlatformAppSettingsModel).where(PlatformAppSettingsModel.platform=='facebook_page'));await s.commit()

async def setup(c):
    r=await c.post(service.BASE+'/settings',json=SETTINGS);assert r.status_code==200,r.text
    r=await c.post(service.BASE+'/start');assert r.status_code==200,r.text
    return parse_qs(urlsplit(r.json()['authorization_url']).query)['state'][0]

@pytest.mark.asyncio
async def test_separate_config_state_session_encryption_selection_and_lifecycle(config,monkeypatch):
    await clear();calls=[]
    async def exchange(code,c):
        calls.append(code);return [FacebookPageCandidate('123','صفحة1',('CREATE_CONTENT',),('pages_show_list',),'PAGE','private-first',int((service.now()+timedelta(days=1)).timestamp()),'source-first'),FacebookPageCandidate('456','صفحة2',('CREATE_CONTENT',),('pages_show_list',),'PAGE','private-chosen',None,'source-chosen')]
    async def facts(c,candidate):return {**candidate.public(),'expires_at':candidate.expires_at}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',facts)
    async with browser() as c:
        state=await setup(c)
        async with browser() as other:
            assert (await other.get(service.BASE+'/callback',params={'state':state,'code':'not-called'})).status_code==400
        assert not calls
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'synthetic-code'});assert r.status_code==303,r.text
        r=await c.get(service.BASE);assert r.json()['pending']['accounts'][1]['page_id']=='456' and 'private-chosen' not in r.text
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'replay'})).status_code==400 and len(calls)==1
        assert (await c.post(service.BASE+'/select',json={'page_id':'999'})).status_code==409
        assert (await c.post(service.BASE+'/select',json={'page_id':'456'})).status_code==200
        row=(await c.get(service.BASE)).json()['connection'];assert row['page_id']=='456' and row['token_type']=='PAGE'
        async with SessionFactory() as s:
            saved=await s.get(Connection,1);assert saved.token_ciphertext!='private-chosen';assert __import__('json').loads(service.key().decrypt(saved.token_ciphertext.encode()))['page_token']=='private-chosen'
        assert (await c.post(service.BASE+'/state',json={'enabled':False})).status_code==200
        assert (await c.post(service.BASE+'/verify')).status_code==200
        assert (await c.get(service.BASE)).json()['connection']['state']=='DISABLED'
        assert (await c.post(service.BASE+'/state',json={'enabled':True})).status_code==200
        assert (await c.post(service.BASE+'/disconnect')).json()['remote_revoked'] is False
        assert (await c.get(service.BASE)).json()['connection'] is None

@pytest.mark.asyncio
async def test_explicit_config_and_owner_same_origin(config):
    await clear()
    async with browser() as c:
        assert (await c.post(service.BASE+'/start')).status_code==409
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'config_reviewed':False})).status_code==409
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'config_reviewed':'yes'})).status_code==422
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'redirect_uri':'https://evil.invalid/api/connections/facebook/callback'})).status_code==409
        assert (await c.post(service.BASE+'/settings',json=SETTINGS,headers={'Origin':'https://evil.invalid'})).status_code==403

@pytest.mark.asyncio
async def test_config_change_invalidates_flow_without_touching_unified(config,monkeypatch):
    from app.application import instagram_oauth as unified
    await clear()
    async with SessionFactory() as s:before=await unified.configuration_for(s)
    async with browser() as c:
        state=await setup(c)
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'config_id':'777777'})).status_code==200
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'not-called'})).status_code==400
    async with SessionFactory() as s:assert (await unified.configuration_for(s))['fingerprint']==before['fingerprint']

@pytest.mark.asyncio
async def test_selection_provider_failure_preserves_saved_row(config,monkeypatch):
    from app.adapters.publishing.facebook_page_login import FacebookLoginError
    await clear()
    async def exchange(code,c):return [FacebookPageCandidate('123','صفحة',('CREATE_CONTENT',),('pages_show_list',),'PAGE','private-page',None,'source-private')]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'page_id':'123'})
        old=(await c.get(service.BASE)).json()['connection']
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        async def bad(c,candidate):raise FacebookLoginError('bad')
        monkeypatch.setattr(service,'selected_facts',bad)
        assert (await c.post(service.BASE+'/select',json={'page_id':'123'})).status_code==409
        assert (await c.get(service.BASE)).json()['connection']==old

@pytest.mark.asyncio
async def test_failed_verify_does_not_reenable_and_prevents_toggle(config,monkeypatch):
    from app.adapters.publishing.facebook_page_login import FacebookLoginError
    await clear()
    async def exchange(code,c):return [FacebookPageCandidate('123','صفحة',('CREATE_CONTENT',),('pages_show_list',),'PAGE','private-page',None,'source-private')]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'page_id':'123'})
        await c.post(service.BASE+'/state',json={'enabled':False})
        async def bad(c,candidate):raise FacebookLoginError('bad')
        monkeypatch.setattr(service,'selected_facts',bad)
        assert (await c.post(service.BASE+'/verify')).status_code==409
        assert (await c.get(service.BASE)).json()['connection']['enabled'] is False
        assert (await c.post(service.BASE+'/state',json={'enabled':True})).status_code==409

@pytest.mark.asyncio
async def test_expired_flow_cancel_and_no_execution_route(config,monkeypatch):
    await clear();calls=[]
    async def forbidden(*a,**kw):calls.append(True);raise AssertionError()
    monkeypatch.setattr(service,'exchange',forbidden)
    async with browser() as c:
        state=await setup(c)
        async with SessionFactory() as s:
            f=await s.get(Flow,service.digest(state));f.expires_at=service.now()-timedelta(seconds=1);await s.commit()
        assert (await c.get(service.BASE+'/callback',params={'state':state,'code':'expired'})).status_code==400
        state=await setup(c)
        assert (await c.get(service.BASE+'/callback',params={'state':state,'error':'denied'})).status_code==400
        assert (await c.post(service.BASE+'/publish',json={})).status_code==404
    assert calls==[]

@pytest.mark.asyncio
async def test_corrupt_encrypted_saved_payload_fails_closed(config,monkeypatch):
    await clear()
    async def exchange(code,c):return [FacebookPageCandidate('123','صفحة',('CREATE_CONTENT',),('pages_show_list',),'PAGE','private-page',None,'source-private')]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'page_id':'123'})
        async with SessionFactory() as s:
            row=await s.get(Connection,1);row.token_ciphertext=service.key().encrypt(b'[]').decode();await s.commit()
        assert (await c.post(service.BASE+'/verify')).status_code==409
        assert (await c.get(service.BASE)).json()['connection']['last_check_ok'] is False
        assert (await c.post(service.BASE+'/state',json={'enabled':True})).status_code==409

@pytest.mark.asyncio
async def test_corrupt_pending_payload_keeps_existing_binding(config,monkeypatch):
    await clear()
    async def exchange(code,c):return [FacebookPageCandidate('123','صفحة',('CREATE_CONTENT',),('pages_show_list',),'PAGE','private-page',None,'source-private')]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'page_id':'123'})
        old=(await c.get(service.BASE)).json()['connection']
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        async with SessionFactory() as s:
            row=await s.get(Flow,service.digest(state));row.token_ciphertext=service.key().encrypt(b'[{}]').decode();await s.commit()
        assert (await c.post(service.BASE+'/select',json={'page_id':'123'})).status_code==409
        assert (await c.get(service.BASE)).json()['connection']==old

@pytest.mark.asyncio
@pytest.mark.parametrize('failure,expected',[(service.OAuthFailure('TOKEN_EXCHANGE'),'TOKEN_EXCHANGE'),(service.OAuthFailure('SESSION'),'SESSION'),(service.OAuthFailure('PERMISSIONS'),'PERMISSIONS'),(service.OAuthFailure('NO_ELIGIBLE_ACCOUNT'),'NO_ELIGIBLE_ACCOUNT')])
async def test_callback_safe_phase_diagnostics(config,monkeypatch,caplog,failure,expected):
    await clear()
    async def bad(*a,**kw):raise failure
    monkeypatch.setattr(service,'exchange',bad)
    async with browser() as c:
        state=await setup(c)
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'do-not-leak-code'})
        assert r.status_code==400 and expected in r.text
        assert 'do-not-leak-code' not in r.text and state not in r.text
        assert 'do-not-leak-code' not in caplog.text and state not in caplog.text
        assert (await c.get(service.BASE)).json()['connection'] is None
        assert 'no-store' in r.headers['cache-control']

@pytest.mark.asyncio
async def test_arbitrary_discovery_error_is_not_reflected(config,monkeypatch,caplog):
    from app.adapters.publishing.facebook_page_login import FacebookLoginError
    await clear()
    async def bad(*a,**kw):raise FacebookLoginError('provider-private-token-and-details')
    monkeypatch.setattr(service,'exchange',bad)
    async with browser() as c:
        state=await setup(c)
        r=await c.get(service.BASE+'/callback',params={'state':state,'code':'private-code'})
        assert r.status_code==400 and 'DISCOVERY' in r.text
        assert 'provider-private' not in r.text+caplog.text
