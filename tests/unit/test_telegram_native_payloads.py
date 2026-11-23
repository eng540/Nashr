import pytest
from app.domain.telegram_payloads import native_payload
from app.adapters.publishing.telegram import TelegramPublisher
from tests.unit.test_telegram_publisher_media import FakeAsyncClient

@pytest.mark.parametrize('value,method',[
 ({'type':'POLL','question':'Question','options':['A','B']},'sendPoll'),
 ({'type':'LOCATION','latitude':0,'longitude':0},'sendLocation'),
 ({'type':'VENUE','latitude':0,'longitude':0,'title':'Test','address':'Test'},'sendVenue'),
 ({'type':'CONTACT','phone_number':'+000000','first_name':'Test'},'sendContact'),
 ({'type':'DICE','emoji':'🎲'},'sendDice'),
])
@pytest.mark.asyncio
async def test_native_methods(monkeypatch,value,method):
 FakeAsyncClient.calls=[];monkeypatch.setattr('app.adapters.publishing.telegram.httpx.AsyncClient',FakeAsyncClient)
 await TelegramPublisher(token='test-only').publish(destination='private-fixture',content='title',native=value)
 url,request=FakeAsyncClient.calls[0];assert url.endswith('/'+method);assert request['json']['chat_id']=='private-fixture'
 assert 'type' not in request['json'] or request['json']['type']=='regular'

@pytest.mark.parametrize('value',[
 {'type':'DICE','chat_id':'other'}, {'type':'LOCATION','latitude':True,'longitude':0},
 {'type':'LOCATION','latitude':float('nan'),'longitude':0}, {'type':'POLL','question':'Q','options':['A']},
 {'type':'CONTACT','first_name':'name'}, {'type':'INVOICE'},
])
def test_native_payload_is_allowlisted(value):
 with pytest.raises(ValueError):native_payload(value)


@pytest.mark.parametrize("value", [{"type": []}, {"type": "DICE", "emoji": []}])
def test_malformed_native_fields_fail_cleanly(value):
    with pytest.raises(ValueError):
        native_payload(value)
