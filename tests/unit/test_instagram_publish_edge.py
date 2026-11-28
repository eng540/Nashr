import httpx
import pytest
from app.adapters.publishing.instagram import InstagramPublisher,InstagramProviderError

@pytest.mark.asyncio
async def test_single_image_exact_caption_and_alt_no_token_in_url():
    seen=[]
    async def handler(request):
        seen.append(request)
        assert request.headers['authorization']=='Bearer synthetic-only'
        assert 'access_token' not in str(request.url)
        return httpx.Response(200,json={'id':'200'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p=InstagramPublisher(client=client,token='synthetic-only',account_id='100')
        assert await p.create_container(kind='IMAGE',media_url='https://media.example.com/synthetic.jpg',caption='نص كامل',alt_text='وصف راجعه المستخدم')=='200'
    assert len(seen)==1 and seen[0].url.path=='/v27.0/100/media'

@pytest.mark.asyncio
async def test_publish_only_finished_and_one_mutation():
    seen=[]
    async def handler(request):
        seen.append((request.method,request.url.path))
        return httpx.Response(200,json={'id':'200','status_code':'FINISHED'} if request.method=='GET' else {'id':'300'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        assert await InstagramPublisher(client=c,token='synthetic',account_id='100').publish_container('200')=='300'
    assert seen==[('GET','/v27.0/200'),('POST','/v27.0/100/media_publish')]

@pytest.mark.asyncio
@pytest.mark.parametrize('state',['IN_PROGRESS','EXPIRED','ERROR','PUBLISHED'])
async def test_non_finished_is_never_published(state):
    async def handler(request):
        assert request.method=='GET'
        return httpx.Response(200,json={'id':'200','status_code':state})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(InstagramProviderError):await InstagramPublisher(client=c,token='synthetic',account_id='100').publish_container('200')

@pytest.mark.asyncio
async def test_mutation_timeout_is_unknown_and_not_retried_or_leaked():
    calls=[]
    async def handler(request):
        calls.append(request);raise httpx.ReadTimeout('untrusted diagnostics secret',request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(InstagramProviderError) as e:await InstagramPublisher(client=c,token='synthetic',account_id='100').create_container(kind='VIDEO',media_url='https://media.example.com/synthetic.mp4',caption='اختبار',share_to_feed=False)
    assert e.value.outcome_unknown and 'secret' not in str(e.value) and len(calls)==1

@pytest.mark.asyncio
async def test_limits_private_url_and_reels_alt_block_before_network():
    async def handler(request):raise AssertionError('Must not send')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p=InstagramPublisher(client=c,token='synthetic',account_id='100')
        for url in ['http://media.example.com/a','https://127.0.0.1/a','https://localhost/a','https://user:pass@example.com/a']:
            with pytest.raises(ValueError):await p.create_container(kind='IMAGE',media_url=url,caption='x')
        with pytest.raises(ValueError):await p.create_container(kind='IMAGE',media_url='https://media.example.com/a',caption='x'*2201)
        with pytest.raises(ValueError):await p.create_container(kind='VIDEO',media_url='https://media.example.com/a',caption='x',alt_text='not supported')

@pytest.mark.asyncio
async def test_server_error_unknown_but_explicit_auth_requires_reconnect():
    async def handler(request):return httpx.Response(500,json={'error':{'code':2,'message':'do not reflect'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p=InstagramPublisher(client=c,token='synthetic',account_id='100')
        with pytest.raises(InstagramProviderError) as e:await p.create_container(kind='IMAGE',media_url='https://media.example.com/a',caption='x')
        assert e.value.outcome_unknown
    async def auth(request):return httpx.Response(400,json={'error':{'code':190}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(auth)) as c:
        with pytest.raises(InstagramProviderError,match='RECONNECT_REQUIRED'):await InstagramPublisher(client=c,token='synthetic',account_id='100').container_status('200')

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',[None,'expired','wrong-app','missing-scope','wrong-account','paging'])
async def test_read_only_selected_account_verification_never_expands_scope(failure):
    import time
    seen=[]
    async def handler(request):
        seen.append(request);assert request.method=='GET'
        if request.url.path.endswith('/debug_token'):
            assert request.headers['authorization']=='Bearer synthetic-app-token'
            return httpx.Response(200,json={'data':{'is_valid':True,'app_id':'999' if failure=='wrong-app' else '123','scopes':['instagram_basic'] if failure=='missing-scope' else ['instagram_basic','instagram_content_publish'],'expires_at':int(time.time())-1 if failure=='expired' else int(time.time())+600}})
        assert request.headers['authorization']=='Bearer synthetic-user-token'
        if request.url.path.endswith('/me'):return httpx.Response(200,json={'client_business_id':'555','id':'777'})
        return httpx.Response(200,json={'data':[{'id':'999' if failure=='wrong-account' else '100','username':'synthetic'}],**({'paging':{'next':'https://untrusted.invalid/next'}} if failure=='paging' else {})})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p=InstagramPublisher(client=c,token='synthetic-user-token',account_id='100')
        if failure:
            with pytest.raises(InstagramProviderError):await p.verify_account(app_access_token='synthetic-app-token',expected_app_id='123')
        else:
            data=await p.verify_account(app_access_token='synthetic-app-token',expected_app_id='123')
            assert data['account_id']=='100' and data['client_business_id']=='555' and data['execution_authorized'] is False
    assert len(seen)<=3 and all(r.url.host=='graph.facebook.com' for r in seen)

@pytest.mark.asyncio
async def test_claimed_publish_edge_is_one_post_no_hidden_status_read():
    seen=[]
    async def handler(request):
        seen.append((request.method,request.url.path,request.content))
        assert request.method=='POST'
        return httpx.Response(200,json={'id':'300'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler))as c:
        result=await InstagramPublisher(client=c,token='synthetic',account_id='100').publish_claimed_container('200')
    assert result=='300' and seen==[('POST','/v27.0/100/media_publish',b'creation_id=200')]

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['timeout','server','malformed','invalid-id'])
async def test_claimed_publish_unknown_never_retries(kind):
    seen=[]
    async def handler(request):
        seen.append(request)
        if kind=='timeout':raise httpx.ReadTimeout('untrusted secret diagnostics',request=request)
        if kind=='server':return httpx.Response(500,json={'error':{'code':2}})
        if kind=='malformed':return httpx.Response(200,content=b'not-json')
        return httpx.Response(200,json={'id':'not-id'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler))as c:
        with pytest.raises(InstagramProviderError)as error:
            await InstagramPublisher(client=c,token='synthetic',account_id='100').publish_claimed_container('200')
    assert error.value.outcome_unknown and len(seen)==1 and 'secret'not in str(error.value)
