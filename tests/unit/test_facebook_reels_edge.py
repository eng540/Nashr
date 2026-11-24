import hashlib,json
import httpx,pytest
from app.adapters.publishing.facebook_reels import FacebookReelsEdge,ReelSession,decode_status,upload_url_valid
from app.adapters.publishing.facebook import FacebookProviderError
DATA=b'synthetic-not-real-mp4';SHA=hashlib.sha256(DATA).hexdigest()
SESSION=ReelSession('123','456','https://rupload.facebook.com/video-upload/456',SHA,len(DATA))
YES=dict(authorized=True,public_page_acknowledged=True,media_transfer_authorized=True)

def state(offset=0,uploaded='in_progress',processed='not_started',published='not_started'):
 return {'status':{'video_status':'processing','uploading_phase':{'status':uploaded,'bytes_transfered':offset},'processing_phase':{'status':processed},'publishing_phase':{'status':published}}}

def edge(c):return FacebookReelsEdge(client=c,token='synthetic-only',page_id='123',version='v27.0')

@pytest.mark.parametrize('url',['http://rupload.facebook.com/video-upload/456','https://evil.invalid/video-upload/456','https://rupload.facebook.com.evil.invalid/video-upload/456','https://rupload.facebook.com@evil.invalid/video-upload/456','https://rupload.facebook.com:443/video-upload/456','https://rupload.facebook.com/video-upload/999','https://rupload.facebook.com/video-upload/456?token=x','https://rupload.facebook.com/video-upload/456#x'])
def test_rejects_untrusted_transfer_destinations(url):assert not upload_url_valid(url,'456','v27.0')

@pytest.mark.asyncio
async def test_explicit_effect_gates_precede_any_traffic():
 seen=[]
 async def handler(r):seen.append(r);raise AssertionError('No traffic')
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  p=edge(c)
  for flags in [{},{'authorized':True},{'authorized':True,'public_page_acknowledged':True}]:
   with pytest.raises(ValueError):await p.initialize(content=DATA,sha256=SHA,mime_type='video/mp4',inspection_confirmed=True,**flags)
   with pytest.raises(ValueError):await p.upload(SESSION,content=DATA,**flags)
   with pytest.raises(ValueError):await p.finish(SESSION,description='exact',**flags)
 assert not seen

@pytest.mark.asyncio
async def test_synthetic_lifecycle_is_separate_phases_and_exact_bytes():
 seen=[];step=0
 async def handler(r):
  nonlocal step
  seen.append(r);assert 'synthetic-only' not in str(r.url)
  if r.url.path.endswith('/me'):return httpx.Response(200,json={'id':'123','name':'synthetic'})
  if r.method=='GET':return httpx.Response(200,json=state(len(DATA),'complete','complete') if step else state(4))
  if r.url.host=='rupload.facebook.com':
   assert r.headers['authorization']=='OAuth synthetic-only' and r.headers['offset']=='4' and r.headers['file_size']==str(len(DATA))
   assert r.content==DATA[4:];step=1;return httpx.Response(200,json={'success':True})
  d=json.loads(r.content)
  if d['upload_phase']=='start':return httpx.Response(200,json={'video_id':'456','upload_url':SESSION.upload_url})
  assert d=={'upload_phase':'finish','video_id':'456','video_state':'PUBLISHED','description':'كامل\nدون قص','title':''}
  return httpx.Response(200,json={'success':True})
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  p=edge(c);s=await p.initialize(content=DATA,sha256=SHA,mime_type='video/mp4',inspection_confirmed=True,**YES);assert s==SESSION
  r=await p.upload(s,content=DATA,offset=4,**YES);assert r['state']=='TRANSFER_ACCEPTED_NOT_PUBLISHED'
  r=await p.finish(s,description='كامل\nدون قص',**YES);assert r['state']=='FINISH_ACCEPTED_NOT_PUBLICATION_VERIFIED' and not r['public_post_verified']
 assert [r.method for r in seen]==['GET','POST','GET','GET','POST','GET','GET','POST']

@pytest.mark.parametrize('body',[{}, {'status':{}},state(-1),state(True),state(len(DATA)+1)])
def test_status_fails_closed(body):
 with pytest.raises(FacebookProviderError):decode_status(body,size_bytes=len(DATA))

def test_complete_phases_are_not_proof_of_publication():
 d=decode_status(state(len(DATA),'complete','complete','complete'),size_bytes=len(DATA));assert d['publishing_complete'] and not d['public_post_verified'] and not d['automatic_retry_allowed']

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['timeout','redirect','badjson','failure','wrongoffset','alreadycomplete'])
async def test_no_retry_or_redirect_after_unknown_write(mode):
 writes=[]
 async def handler(r):
  if r.url.path.endswith('/me'):return httpx.Response(200,json={'id':'123','name':'synthetic'})
  if r.method=='GET':return httpx.Response(200,json=state(3 if mode=='wrongoffset' else 0,'complete' if mode=='alreadycomplete' else 'in_progress'))
  writes.append(r)
  if mode=='timeout':raise httpx.ReadTimeout('private',request=r)
  if mode=='redirect':return httpx.Response(307,headers={'location':'https://evil.invalid/'})
  if mode=='badjson':return httpx.Response(200,text='private')
  return httpx.Response(500,json={'error':{'message':'private'}})
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  with pytest.raises(FacebookProviderError) as exc:await edge(c).upload(SESSION,content=DATA,**YES)
  assert 'private' not in str(exc.value)
 assert len(writes)==(0 if mode in {'wrongoffset','alreadycomplete'} else 1)

@pytest.mark.asyncio
@pytest.mark.parametrize('publishing',['in_progress','complete','error'])
async def test_finish_never_repeats_when_publishing_started(publishing):
 seen=[]
 async def handler(r):seen.append(r);return httpx.Response(200,json=state(len(DATA),'complete','complete',publishing))
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  with pytest.raises(FacebookProviderError):await edge(c).finish(SESSION,description='exact',**YES)
 assert [x.method for x in seen]==['GET']

@pytest.mark.asyncio
async def test_missing_remote_offset_does_not_assume_zero():
 body=state();del body['status']['uploading_phase']['bytes_transfered']
 async def handler(r):assert r.method=='GET';return httpx.Response(200,json=body)
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  with pytest.raises(FacebookProviderError):await edge(c).upload(SESSION,content=DATA,**YES)

@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['wrongpage','wronghash','wrongbytes','badurl','zero','boolsize'])
async def test_pinned_inputs_fail_before_network(mutation):
 from dataclasses import replace
 session=SESSION;content=DATA
 if mutation=='wrongpage':session=replace(session,page_id='999')
 if mutation=='wronghash':session=replace(session,sha256='0'*64)
 if mutation=='wrongbytes':content=DATA+b'x'
 if mutation=='badurl':session=replace(session,upload_url='https://evil.invalid/')
 if mutation=='zero':session=replace(session,size_bytes=0)
 if mutation=='boolsize':session=replace(session,size_bytes=True)
 async def handler(r):raise AssertionError('No traffic')
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  with pytest.raises(ValueError):await edge(c).upload(session,content=content,**YES)

@pytest.mark.asyncio
async def test_missing_offset_only_allowed_for_never_transferred_initial_session():
 calls=[]
 def handler(req):
  if req.url.host=='rupload.facebook.com':calls.append('upload');return httpx.Response(200,json={'success':True})
  if req.url.path.endswith('/me'):return httpx.Response(200,json={'id':'123','name':'Page'})
  return httpx.Response(200,json={'status':{'video_status':'uploading','uploading_phase':{'status':'in_progress'},'processing_phase':{'status':'not_started'},'publishing_phase':{'status':'not_started'}}})
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  with pytest.raises(FacebookProviderError):await edge(c).upload(SESSION,content=DATA,**YES)
  assert not calls
  await edge(c).upload(SESSION,content=DATA,initial_transfer=True,**YES)
  assert calls==['upload']

def test_documented_completed_spelling_supported():
 assert decode_status(state(len(DATA),'completed','completed','completed'),size_bytes=len(DATA))['publishing_complete']

@pytest.mark.asyncio
async def test_finish_accepts_exact_upload_complete_before_processing_starts():
 calls=[]
 def handler(req):
  if req.method=='POST':calls.append('finish');return httpx.Response(200,json={'success':True})
  if req.url.path.endswith('/me'):return httpx.Response(200,json={'id':'123','name':'Page'})
  return httpx.Response(200,json={'status':{'video_status':'upload_complete','uploading_phase':{'status':'complete','bytes_transferred':len(DATA)},'processing_phase':{'status':'not_started'},'publishing_phase':{'status':'not_started'}}})
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
  await edge(c).finish(SESSION,description='exact',**YES)
 assert calls==['finish']
