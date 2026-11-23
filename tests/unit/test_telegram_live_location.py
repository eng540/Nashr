import pytest
from app.domain.telegram_payloads import native_payload


@pytest.mark.parametrize('period',[60,86400])
def test_bounded_live_location(period):
    method,data=native_payload({'type':'LIVE_LOCATION','latitude':0,'longitude':0,'live_period':period})
    assert method=='sendLocation' and data['live_period']==period


@pytest.mark.parametrize('period',[0,59,86401,2147483647,True,60.1,None])
def test_reject_unbounded_or_invalid_live_location(period):
    with pytest.raises(ValueError):native_payload({'type':'LIVE_LOCATION','latitude':0,'longitude':0,'live_period':period})


@pytest.mark.asyncio
async def test_update_and_stop_target_original_message(monkeypatch):
    from app.adapters.publishing.telegram import TelegramPublisher
    from tests.unit.test_telegram_publisher_media import FakeAsyncClient
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'ok':True,'result':{'message_id':321}}
    class Client(FakeAsyncClient):
        async def post(self,url,**kwargs):self.calls.append((url,kwargs));return Response()
    Client.calls=[]
    monkeypatch.setattr('app.adapters.publishing.telegram.httpx.AsyncClient',Client)
    pub=TelegramPublisher(token='fixture')
    await pub.update_live_location(destination='private',message_id='321',action='UPDATE',payload={'latitude':.001,'longitude':0})
    await pub.update_live_location(destination='private',message_id='321',action='STOP',payload={})
    assert Client.calls[0][0].endswith('/editMessageLiveLocation')
    assert Client.calls[0][1]['json']=={'chat_id':'private','message_id':321,'latitude':.001,'longitude':0}
    assert Client.calls[1][0].endswith('/stopMessageLiveLocation')
    assert Client.calls[1][1]['json']=={'chat_id':'private','message_id':321}
