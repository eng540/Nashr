from uuid import uuid4
import pytest
from app.domain.telegram_albums import album_ids, validate_album_group


@pytest.mark.parametrize('kinds', [['IMAGE','VIDEO'], ['AUDIO']*2, ['DOCUMENT']*10])
def test_supported_groups(kinds):
    validate_album_group(kinds)


@pytest.mark.parametrize('kinds', [['IMAGE'], ['IMAGE']*11, ['AUDIO','VIDEO'], ['DOCUMENT','IMAGE'], ['STICKER','STICKER']])
def test_reject_bad_groups(kinds):
    with pytest.raises(ValueError):
        validate_album_group(kinds)


def test_ids_require_unique_bounded_uuid_list_and_no_instructions():
    ids = [str(uuid4()), str(uuid4())]
    assert len(album_ids({'artifact_ids': ids})) == 2
    for payload in [{'artifact_ids': [ids[0]]*2}, {'artifact_ids': [None, ids[0]]}, {'artifact_ids': ['bad', ids[0]]}, {'artifact_ids': ids, 'chat_id': 'other'}]:
        with pytest.raises(ValueError):
            album_ids(payload)


@pytest.mark.asyncio
async def test_album_adapter_uses_multipart_and_retains_all_ids(monkeypatch):
    import json
    from app.adapters.publishing.telegram import TelegramPublisher
    from tests.unit.test_telegram_publisher_media import FakeAsyncClient
    class Response:
        def raise_for_status(self): pass
        def json(self):return {'ok':True,'result':[{'message_id':12},{'message_id':13}]}
    class Client(FakeAsyncClient):
        async def post(self,url,**kwargs):
            self.calls.append((url,kwargs));return Response()
    Client.calls=[]
    monkeypatch.setattr('app.adapters.publishing.telegram.httpx.AsyncClient',Client)
    result=await TelegramPublisher(token='fixture').publish(destination='private',content='',album=[{'kind':'IMAGE','data':b'png','mime_type':'image/png','caption':'one'},{'kind':'VIDEO','data':b'mp4','mime_type':'video/mp4','caption':'two'}])
    assert result.external_ids==('12','13')
    url,request=Client.calls[0]
    assert url.endswith('/sendMediaGroup')
    assert set(request['data'])=={'chat_id','media'}
    entries=json.loads(request['data']['media'])
    assert [v['type'] for v in entries]==['photo','video']
    assert entries[0]['media']=='attach://media0'
    assert len(request['files'])==2
