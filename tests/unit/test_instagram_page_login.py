import httpx
import pytest
from app.adapters.publishing.instagram_page_login import PageLinkedLogin,PageLoginError,REQUIRED

def page(**kw):return {'id':'123','name':'صفحة مقترحة','tasks':['CREATE_CONTENT'],'access_token':'private-page-token','instagram_business_account':{'id':'456','username':'creator'},**kw}

def client(pages=None,debug=None,selected=None):
    calls=[]
    def route(r):
        calls.append(r)
        if r.url.path.endswith('debug_token'):
            typ='PAGE' if r.url.params.get('input_token')=='private-page-token' else 'USER'
            return httpx.Response(200,json={'data':{'is_valid':True,'app_id':'999','type':typ,'scopes':sorted(REQUIRED),'expires_at':0,**(debug or {})}})
        if r.url.path.endswith('me/accounts'):return httpx.Response(200,json=pages or {'data':[page()]})
        return httpx.Response(200,json=selected or page())
    return httpx.AsyncClient(transport=httpx.MockTransport(route)),calls

@pytest.mark.asyncio
async def test_discover_verify_public_no_token_and_no_writes():
    c,calls=client()
    async with c:
        login=PageLinkedLogin(client=c,app_id='999',app_secret='private-app-secret');candidates=await login.discover('private-user-token')
        assert len(candidates)==1 and 'private-page-token' not in repr(candidates)
        assert 'token' not in candidates[0].public() and not candidates[0].public()['execution_authorized']
        facts=await login.verify_selected(candidates[0]);assert facts['page_id']=='123' and not facts['execution_authorized']
    assert all(r.method=='GET' and r.url.host=='graph.facebook.com' for r in calls)
    assert all('private-page-token' not in str(r.url) for r in calls if not r.url.path.endswith('debug_token'))

@pytest.mark.asyncio
@pytest.mark.parametrize('debug',[{'type':'SYSTEM_USER'},{'app_id':'888'},{'is_valid':False},{'scopes':['instagram_basic']},{'expires_at':1},{'expires_at':True}])
async def test_reject_wrong_token_identity_expiry_or_permissions(debug):
    c,_=client(debug=debug)
    async with c:
        with pytest.raises(PageLoginError):await PageLinkedLogin(client=c,app_id='999',app_secret='s').discover('u')

@pytest.mark.asyncio
@pytest.mark.parametrize('pages',[{'data':[page(tasks=['ADVERTISE'])]},{'data':[page()],'paging':{'next':'https://evil.invalid'}},{'data':[page(),page()]},{'data':[page(access_token='')]},{'data':[page(instagram_business_account=None)]}])
async def test_discovery_never_guesses_or_follows_pagination(pages):
    c,_=client(pages=pages)
    async with c:
        with pytest.raises(PageLoginError):await PageLinkedLogin(client=c,app_id='999',app_secret='s').discover('u')

@pytest.mark.asyncio
async def test_selected_page_account_mismatch_rejected():
    c,_=client(selected=page(id='777'))
    async with c:
        login=PageLinkedLogin(client=c,app_id='999',app_secret='s');candidate=(await login.discover('u'))[0]
        with pytest.raises(PageLoginError):await login.verify_selected(candidate)

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['redirect','invalid','lost'])
async def test_external_failure_sanitized_no_redirect_follow_or_writes(kind):
    calls=[]
    def route(r):
        calls.append(r)
        if kind=='lost':raise httpx.ConnectError('private upstream diagnostic',request=r)
        if kind=='invalid':return httpx.Response(200,text='private diagnostic')
        return httpx.Response(302,headers={'Location':'https://evil.invalid/private'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as c:
        with pytest.raises(PageLoginError) as exc:await PageLinkedLogin(client=c,app_id='999',app_secret='s').discover('u')
    assert len(calls)==1 and str(exc.value)=='META_PAGE_LOGIN_READ_FAILED'

@pytest.mark.asyncio
async def test_known_earlier_expiry_not_erased_by_page_expiry_unknown():
    import time
    deadline=int(time.time())+300
    c,_=client(debug={'expires_at':deadline})
    async with c:
        login=PageLinkedLogin(client=c,app_id='999',app_secret='s')
        candidate=(await login.discover('u'))[0]
        result=await login.verify_selected(candidate)
        assert result['expires_at']==deadline
