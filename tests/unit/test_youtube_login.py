import pytest
import httpx
from app.adapters.publishing import youtube_login as login
CID='UC'+'a'*22

def token(**kw):
    return dict(access_token='private-access',refresh_token='private-refresh',expires_in=3600,token_type='Bearer',scope=login.SCOPE,**kw)

def test_tokens_exact_scope_refresh_and_expiry():
    assert login.tokens(token())['refresh_token']=='private-refresh'
    b=token();b.pop('refresh_token');assert login.tokens(b,previous_refresh='old')['refresh_token']=='old'
    for change in [{'scope':login.SCOPE+' https://www.googleapis.com/auth/youtube.upload'},{'scope':''},{'refresh_token':''},{'expires_in':True},{'refresh_token_expires_in':0}]:
        with pytest.raises(ValueError):login.tokens({**token(),**change})
    with pytest.raises(ValueError):login.tokens(b)

@pytest.mark.asyncio
async def test_readonly_exchange_and_complete_channels():
    seen=[]
    def handle(r):
        seen.append(r)
        if r.url.path.endswith('/token'):return httpx.Response(200,json=token())
        return httpx.Response(200,json={'items':[{'id':CID,'snippet':{'title':'القناة'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
        t=await login.exchange(c,dict(client_id='id',client_secret='secret',redirect_uri='https://test/callback'),'code')
        assert (await login.channels(c,t['access_token']))==[{'channel_id':CID,'title':'القناة'}]
        assert (await login.refresh(c,dict(client_id='id',client_secret='secret'),'old'))['refresh_token']=='private-refresh'
    assert all(r.url.path in ['/token','/youtube/v3/channels'] for r in seen)
    assert seen[1].method=='GET'

@pytest.mark.asyncio
@pytest.mark.parametrize('body',[{}, {'items':[]},{'items':[{'id':CID,'snippet':{'title':'x'}}],'nextPageToken':'more'}, {'items':[{'id':CID,'snippet':{'title':'x'}}]*2},{'items':[{'id':'bad','snippet':{'title':'x'}}]}])
async def test_incomplete_or_ambiguous_identity_rejected(body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body))) as c:
        with pytest.raises(ValueError):await login.channels(c,'token')
