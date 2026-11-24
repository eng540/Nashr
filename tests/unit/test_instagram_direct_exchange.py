import httpx,pytest
from urllib.parse import parse_qs
from app.application import instagram_direct_oauth as s

SETTINGS=dict(app_id='123',app_secret='synthetic-secret',redirect_uri='https://test/api/connections/instagram-direct/callback')

def transport(*,uid='456',me='456',permissions=None,expiry=5000,fail=None):
    calls=[]
    def route(r):
        calls.append(r)
        if fail=='redirect':return httpx.Response(302,headers={'Location':'https://evil.invalid'})
        if fail=='network':raise httpx.ConnectError('private upstream',request=r)
        if r.url.host=='api.instagram.com':return httpx.Response(200,json={'data':[{'access_token':'private-short','user_id':uid,'permissions':','.join(sorted(s.SCOPES)) if permissions is None else permissions}]})
        if r.url.path=='/access_token':return httpx.Response(200,json={'access_token':'private-long','token_type':'bearer','expires_in':expiry})
        return httpx.Response(200,json={'data':[{'id':me,'user_id':'789','username':'creator'}]})
    return httpx.MockTransport(route),calls

@pytest.mark.asyncio
async def test_exchange_fixed_instagram_hosts_only_and_identity(monkeypatch):
    t,calls=transport();original=httpx.AsyncClient
    monkeypatch.setattr(s.httpx,'AsyncClient',lambda **kw:original(transport=t,**kw))
    token,account,scopes,expiry=await s.exchange('private-code',SETTINGS)
    assert token=='private-long' and account=={'account_id':'789','username':'creator','app_scoped_id':'456'} and set(scopes)==s.SCOPES
    assert 4900<(expiry-s.now()).total_seconds()<5100
    assert [(r.method,r.url.host) for r in calls]==[('POST','api.instagram.com'),('GET','graph.instagram.com'),('GET','graph.instagram.com')]
    form=parse_qs(calls[0].content.decode());assert form['client_id']==['123'] and form['code']==['private-code']
    assert calls[-1].headers['Authorization']=='Bearer private-long'
    assert all('facebook.com' not in r.url.host for r in calls)

@pytest.mark.asyncio
@pytest.mark.parametrize('params,reason',[({'me':'999'},'IDENTITY'),({'permissions':'instagram_business_basic'},'PERMISSIONS'),({'expiry':0},'EXPIRY'),({'expiry':True},'EXPIRY'),({'expiry':7000000},'EXPIRY'),({'fail':'redirect'},'TOKEN_EXCHANGE'),({'fail':'network'},'TOKEN_EXCHANGE')])
async def test_exchange_fails_closed_sanitized(monkeypatch,params,reason):
    t,calls=transport(**params);original=httpx.AsyncClient
    monkeypatch.setattr(s.httpx,'AsyncClient',lambda **kw:original(transport=t,**kw))
    with pytest.raises(s.DirectFailure) as e:await s.exchange('private-code',SETTINGS)
    assert e.value.reason==reason and 'private' not in str(e.value)
    assert len(calls)<=3

@pytest.mark.parametrize('body',[{'data':[]},{'data':[{},{}]},{'user_id':'bad','username':'u'},{'user_id':'123','username':'bad space'},{'user_id':True,'username':'u'}])
def test_identity_rejects_ambiguous_or_bad_data(body):
    with pytest.raises(s.DirectFailure):s.identity(body)
