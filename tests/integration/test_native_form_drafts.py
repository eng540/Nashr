from uuid import uuid4
import httpx
import pytest
from app.api.auth import SESSION_COOKIE, issue_token
from app.main import app

@pytest.mark.parametrize('native',[
 {'type':'POLL','question':'اختر جوابًا','options':['الأول','الثاني'],'allows_multiple_answers':True},
 {'type':'LOCATION','latitude':21.5,'longitude':39},
 {'type':'LIVE_LOCATION','latitude':21.5,'longitude':39,'live_period':120},
 {'type':'VENUE','latitude':21.5,'longitude':39,'title':'مكان مختار','address':'عنوان للمراجعة'},
 {'type':'CONTACT','first_name':'جهة مختارة','phone_number':'+966500000001'},
 {'type':'DICE','emoji':'🎯'},
])
async def test_labeled_form_payload_persists_exact_native_draft_without_publication(native,monkeypatch):
 monkeypatch.setenv('NASHR_AUTH_PASSWORD','unit-test-only')
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
  client.cookies.set(SESSION_COOKIE,issue_token('admin'))
  response=await client.post('/api/artifacts/manual-draft',json={'kind':'TEXT','title':'Form fixture '+str(uuid4()),'content':'وصف داخلي للمراجعة','native':native})
  assert response.status_code==201,response.text
  saved=response.json();assert saved['review_status']=='DRAFT';assert saved['metadata']['telegram_native']==native
  history=await client.get('/api/artifacts/'+saved['id']+'/publications')
  assert history.status_code==200 and history.json()['items']==[]
