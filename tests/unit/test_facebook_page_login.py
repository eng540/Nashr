import httpx,pytest
from app.adapters.publishing.facebook_page_login import FacebookPagesLogin,FacebookLoginError,REQUIRED

def provider(*,mode='SYSTEM_USER',tasks=None,scopes=None,page_id='123',token_type=None,paging=None,fail=False):
    calls=[]
    def handler(r):
        calls.append(r)
        assert r.method=='GET'
        path=r.url.path
        if fail:return httpx.Response(400,json={'error':{'message':'private-token'}})
        if path.endswith('/debug_token'):
            t=r.url.params['input_token'];return httpx.Response(200,json={'data':{'is_valid':True,'app_id':'123456','type':token_type or ('PAGE' if t=='page-private' else mode),'scopes':list(REQUIRED if scopes is None else scopes),'expires_at':0}})
        if path.endswith('/me/accounts'):return httpx.Response(200,json={'data':[{'id':'123','name':'Page','tasks':['CREATE_CONTENT'] if tasks is None else tasks,'access_token':'page-private'}],'paging':paging or {}})
        if path.endswith('/me') and r.url.params.get('fields')=='client_business_id':return httpx.Response(200,json={'client_business_id':'456'})
        if path.endswith('/me'):return httpx.Response(200,json={'id':page_id,'name':'Page'})
        raise AssertionError(path)
    c=httpx.AsyncClient(transport=httpx.MockTransport(handler));return FacebookPagesLogin(client=c,app_id='123456',app_secret='secret',token_mode=mode),c,calls

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['USER','SYSTEM_USER'])
async def test_read_only_discovery_and_pinned_page_verification(mode):
    p,c,calls=provider(mode=mode)
    async with c:
        rows=await p.discover('source-private');assert rows[0].page_id=='123'
        assert 'private' not in repr(rows[0]) and 'private' not in str(rows[0].public())
        result=await p.verify_selected(rows[0]);assert result['page_id']=='123' and result['execution_authorized'] is False and result['expires_at'] is None
    assert all(r.method=='GET' for r in calls)
    assert all(r.headers.get('Authorization') for r in calls)
    assert not any('access_token' in r.url.params for r in calls)

@pytest.mark.asyncio
@pytest.mark.parametrize('kw',[{'tasks':['MODERATE']},{'tasks':['MANAGE']},{'scopes':['pages_read_engagement']},{'token_type':'USER'},{'paging':{'next':'https://evil.invalid/private'}},{'fail':True}])
async def test_fail_closed_without_token_leaks(kw):
    p,c,_=provider(**kw)
    async with c:
        with pytest.raises(FacebookLoginError) as e:await p.discover('source-private')
        assert 'private' not in str(e.value)

@pytest.mark.asyncio
async def test_selected_page_token_cannot_silently_switch():
    p,c,_=provider(page_id='999')
    async with c:
        rows=await p.discover('source-private')
        with pytest.raises(FacebookLoginError):await p.verify_selected(rows[0])
