from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import httpx,pytest
from sqlalchemy import delete,select
from app.application import instagram_page_oauth as service
from app.adapters.publishing.instagram_page_login import PageCandidate
from app.infrastructure.database.models import InstagramPageOAuthFlowModel as Flow,InstagramPageConnectionModel as Connection,PlatformAppSettingsModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_instagram_oauth import config,browser

SETTINGS=dict(app_id='123456',app_secret='synthetic-secret',config_id='456789',redirect_uri='https://test/api/connections/instagram-page/callback',user_token_reviewed=True)

async def clear():
    async with SessionFactory() as s:
        await s.execute(delete(Flow));await s.execute(delete(Connection));await s.execute(delete(PlatformAppSettingsModel).where(PlatformAppSettingsModel.platform=='instagram_page'));await s.commit()

async def setup(c):
    r=await c.post(service.BASE+'/settings',json=SETTINGS);assert r.status_code==200,r.text
    r=await c.post(service.BASE+'/start');assert r.status_code==200,r.text
    return parse_qs(urlsplit(r.json()['authorization_url']).query)['state'][0]

@pytest.mark.asyncio
async def test_separate_config_state_session_encryption_selection_and_lifecycle(config,monkeypatch):
    await clear();calls=[]
    async def exchange(code,c):
        calls.append(code);return [PageCandidate('111','first','123','صفحة1',('CREATE_CONTENT',),'private-first',int((service.now()+timedelta(days=1)).timestamp())),PageCandidate('222','chosen','456','صفحة2',('MANAGE',),'private-chosen',None)]
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
        assert (await c.post(service.BASE+'/select',json={'account_id':'999'})).status_code==409
        assert (await c.post(service.BASE+'/select',json={'account_id':'222'})).status_code==200
        row=(await c.get(service.BASE)).json()['connection'];assert row['account_id']=='222' and row['page_id']=='456' and row['token_type']=='PAGE'
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
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'user_token_reviewed':False})).status_code==409
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'user_token_reviewed':'yes'})).status_code==422
        assert (await c.post(service.BASE+'/settings',json={**SETTINGS,'redirect_uri':'https://evil.invalid/api/connections/instagram-page/callback'})).status_code==409
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
    from app.adapters.publishing.instagram_page_login import PageLoginError
    await clear()
    async def exchange(code,c):return [PageCandidate('111','creator','123','صفحة',('CREATE_CONTENT',),'private-page',None)]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'account_id':'111'})
        old=(await c.get(service.BASE)).json()['connection']
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        async def bad(c,candidate):raise PageLoginError('bad')
        monkeypatch.setattr(service,'selected_facts',bad)
        assert (await c.post(service.BASE+'/select',json={'account_id':'111'})).status_code==409
        assert (await c.get(service.BASE)).json()['connection']==old

@pytest.mark.asyncio
async def test_failed_verify_does_not_reenable_and_prevents_toggle(config,monkeypatch):
    from app.adapters.publishing.instagram_page_login import PageLoginError
    await clear()
    async def exchange(code,c):return [PageCandidate('111','creator','123','صفحة',('CREATE_CONTENT',),'private-page',None)]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'account_id':'111'})
        await c.post(service.BASE+'/state',json={'enabled':False})
        async def bad(c,candidate):raise PageLoginError('bad')
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
    async def exchange(code,c):return [PageCandidate('111','creator','123','صفحة',('CREATE_CONTENT',),'private-page',None)]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'account_id':'111'})
        async with SessionFactory() as s:
            row=await s.get(Connection,1);row.token_ciphertext=service.key().encrypt(b'[]').decode();await s.commit()
        assert (await c.post(service.BASE+'/verify')).status_code==409
        assert (await c.get(service.BASE)).json()['connection']['last_check_ok'] is False
        assert (await c.post(service.BASE+'/state',json={'enabled':True})).status_code==409

@pytest.mark.asyncio
async def test_corrupt_pending_payload_keeps_existing_binding(config,monkeypatch):
    await clear()
    async def exchange(code,c):return [PageCandidate('111','creator','123','صفحة',('CREATE_CONTENT',),'private-page',None)]
    async def good(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(service,'exchange',exchange);monkeypatch.setattr(service,'selected_facts',good)
    async with browser() as c:
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'});await c.post(service.BASE+'/select',json={'account_id':'111'})
        old=(await c.get(service.BASE)).json()['connection']
        state=await setup(c);await c.get(service.BASE+'/callback',params={'state':state,'code':'x'})
        async with SessionFactory() as s:
            row=await s.get(Flow,service.digest(state));row.token_ciphertext=service.key().encrypt(b'[{}]').decode();await s.commit()
        assert (await c.post(service.BASE+'/select',json={'account_id':'111'})).status_code==409
        assert (await c.get(service.BASE)).json()['connection']==old
