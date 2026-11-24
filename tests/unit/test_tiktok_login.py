import httpx,pytest
from app.adapters.publishing import tiktok_login as p
def token():return dict(access_token='private-access',refresh_token='private-refresh',open_id='test-id',expires_in=7200,refresh_expires_in=86400,scope='user.info.basic',token_type='Bearer')
@pytest.mark.parametrize('field,value',[('expires_in',True),('expires_in',0),('refresh_expires_in',-1),('scope','user.info.basic,video.publish'),('scope',''),('open_id',''),('token_type','MAC'),('error','invalid_request')])
def test_fail_closed(field,value):
    with pytest.raises(p.TikTokLoginError):p.token_payload({**token(),field:value})
def test_accept_returned_ttls():assert p.token_payload(token())['expires_in']==7200
@pytest.mark.asyncio
async def test_official_form_and_identity_only():
    calls=[]
    async def respond(r):
        calls.append(r)
        if r.method=='POST':return httpx.Response(200,json=token())
        return httpx.Response(200,json={'data':{'user':{'open_id':'test-id','display_name':'Synthetic'}},'error':{'code':'ok'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as c:
        t=await p.exchange(c,dict(client_key='key',client_secret='private-secret',redirect_uri='https://test/callback'),'private-code')
        assert (await p.identity(c,t['access_token'],t['open_id']))=={'open_id':'test-id','display_name':'Synthetic'}
    assert str(calls[0].url)=='https://open.tiktokapis.com/v2/oauth/token/' and calls[0].headers['content-type'].startswith('application/x-www-form-urlencoded')
    assert 'private-code' not in str(calls[0].url) and calls[1].url.params['fields']=='open_id,display_name,avatar_url'
@pytest.mark.asyncio
@pytest.mark.parametrize('data',[{},[],{'error':{'code':'ok'},'data':{'user':{'open_id':'wrong','display_name':'bad'}}},{'error':{'code':'denied'}}])
async def test_bad_identity(data):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data))) as c:
        with pytest.raises(p.TikTokLoginError):await p.identity(c,'secret','test-id')
