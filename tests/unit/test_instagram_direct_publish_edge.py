from datetime import datetime,timedelta,timezone
import httpx,pytest
from app.adapters.publishing.instagram_direct import InstagramDirectPublisher
from app.adapters.publishing.instagram import InstagramProviderError
from app.application.instagram_direct_oauth import SCOPES

@pytest.mark.asyncio
async def test_direct_single_image_reel_and_publish_never_hit_facebook():
    seen=[]
    def route(r):
        seen.append(r);assert r.url.host=='graph.instagram.com';assert r.headers['authorization']=='Bearer synthetic'
        assert 'access_token' not in str(r.url)
        if r.method=='GET':return httpx.Response(200,json={'id':'200','status_code':'FINISHED'})
        return httpx.Response(200,json={'id':'300' if r.url.path.endswith('media_publish') else '200'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as c:
        p=InstagramDirectPublisher(client=c,token='synthetic',account_id='100')
        assert await p.create_container(kind='IMAGE',media_url='https://media.example.com/a.jpg',caption='نص أصلي',alt_text='وصف أصلي')=='200'
        assert await p.create_container(kind='VIDEO',media_url='https://media.example.com/a.mp4',caption='نص فيديو',share_to_feed=False)=='200'
        assert await p.publish_container('200')=='300'
    assert len(seen)==4
    assert b'alt_text=' in seen[0].content and b'share_to_feed=false' in seen[1].content

@pytest.mark.asyncio
@pytest.mark.parametrize('mismatch',[False,True])
async def test_direct_identity_uses_professional_and_scoped_ids(mismatch):
    seen=[]
    def route(r):
        seen.append(r);assert r.url.host=='graph.instagram.com' and r.url.path=='/v27.0/me'
        return httpx.Response(200,json={'id':'888' if mismatch else '456','user_id':'100','username':'creator'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as c:
        p=InstagramDirectPublisher(client=c,token='synthetic',account_id='100')
        args=dict(expected_username='creator',app_scoped_id='456',scopes=sorted(SCOPES),expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        if mismatch:
            with pytest.raises(InstagramProviderError,match='MISMATCH'):await p.verify_account(**args)
        else:assert (await p.verify_account(**args))['execution_authorized'] is False
    assert len(seen)==1

@pytest.mark.asyncio
async def test_direct_unknown_mutation_never_retries_or_leaks():
    seen=[]
    def route(r):seen.append(r);raise httpx.ReadTimeout('private detail',request=r)
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as c:
        p=InstagramDirectPublisher(client=c,token='synthetic',account_id='100')
        with pytest.raises(InstagramProviderError) as e:await p.create_container(kind='IMAGE',media_url='https://media.example.com/a.jpg',caption='original')
        assert e.value.outcome_unknown and 'private' not in str(e.value)
    assert len(seen)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['expired','naive','missing-scope','bad-scope'])
async def test_direct_invalid_saved_facts_block_before_network(failure):
    def route(r):raise AssertionError('Must block before provider read')
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as c:
        p=InstagramDirectPublisher(client=c,token='synthetic',account_id='100')
        expiry=datetime.now(timezone.utc)+timedelta(hours=1)
        scopes=sorted(SCOPES)
        if failure=='expired':expiry=datetime.now(timezone.utc)-timedelta(seconds=1)
        if failure=='naive':expiry=datetime.now()
        if failure=='missing-scope':scopes=['instagram_business_basic']
        if failure=='bad-scope':scopes='instagram_business_basic'
        with pytest.raises(InstagramProviderError):await p.verify_account(expected_username='creator',app_scoped_id='456',scopes=scopes,expires_at=expiry)
