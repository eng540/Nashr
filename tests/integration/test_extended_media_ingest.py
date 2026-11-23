import io
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.api.auth import SESSION_COOKIE, issue_token
from app.application.media_bank import IngestReadyMedia
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.models import ArtifactModel
from app.infrastructure.database.session import SessionFactory
from app.main import app
from tests.integration.test_media_bank_ingest import _FakeS3Client


@pytest.mark.asyncio
async def test_document_audio_voice_gif_sticker_drafts_and_schedules(monkeypatch):
    monkeypatch.setenv('NASHR_AUTH_PASSWORD','unit-test-only')
    monkeypatch.setenv('TELEGRAM_DESTINATION_ID','private-fixture')
    storage=S3ArtifactStorage(client=_FakeS3Client(),bucket='fixture')
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:storage)
    image=io.BytesIO();Image.new('RGBA',(512,512),(0,255,0,255)).save(image,format='WEBP')
    fixtures=[('DOCUMENT','application/pdf',b'%PDF-1.4 test','fixture.pdf'),
      ('AUDIO','audio/mpeg',b'ID3'+b'x'*100,'fixture.mp3'),
      ('VOICE','audio/ogg',b'OggS'+b'OpusHead'+b'x'*100,'fixture.ogg'),
      ('ANIMATION','image/gif',b'GIF89a'+b'x'*100,'fixture.gif'),
      ('STICKER','image/webp',image.getvalue(),'fixture.webp')]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
      client.cookies.set(SESSION_COOKIE,issue_token('admin'))
      for kind,mime,data,name in fixtures:
        r=await client.post('/api/artifacts/ingest-media',files={'file':(name,data,mime)},data={'media_kind':kind,'caption':'Private test'})
        assert r.status_code==201,r.text
        item=r.json();assert item['kind']==kind;assert item['review_status']=='DRAFT'
        if kind=='DOCUMENT':assert item['mime_type']=='application/octet-stream'
        uid=item['id'];assert (await client.post(f'/api/artifacts/{uid}/approve',json={})).status_code==200
        r=await client.post(f'/api/artifacts/{uid}/telegram-media-draft');assert r.status_code==201,r.text
        first=r.json()['id'];assert (await client.post(f'/api/artifacts/{uid}/telegram-media-draft')).json()['id']==first
        r=await client.post(f'/api/artifacts/{uid}/schedule',json={'name':'test','timezone':'Asia/Riyadh','scheduled_at':'2030-01-01T10:00:00+03:00'})
        assert r.status_code==201,r.text
        from app.application.scheduling import validate_schedule_for_activation
        from uuid import UUID
        async with SessionFactory() as session:
            validation=await validate_schedule_for_activation(session,UUID(r.json()['id']))
            assert validation['valid'] and not validation['blocked_items'] and validation['processable_pending_items']==1
      for kind in ['TEXT','QUIZ']:
        payload={'kind':kind,'title':'Private fixture','content':'Which?'}
        if kind=='QUIZ':payload['quiz']={'question':'Which?','options':['one','two'],'correct_option_id':0}
        r=await client.post('/api/artifacts/manual-draft',json=payload);assert r.status_code==201,r.text
        uid=r.json()['id'];assert (await client.post(f'/api/artifacts/{uid}/approve',json={})).status_code==200
        assert (await client.post(f'/api/artifacts/{uid}/telegram-draft')).status_code==201


@pytest.mark.asyncio
async def test_native_content_stays_reviewable_and_sends_expected_payload(monkeypatch):
    from app.application.manual_artifacts import create_manual_artifact
    from app.application.generic_artifact_review import GenericArtifactReviewService
    from app.application.publications import CreateTelegramDraft, ApproveAndPublish
    from app.adapters.publishing.telegram import TelegramPublisher
    from tests.unit.test_telegram_publisher_media import FakeAsyncClient
    monkeypatch.setattr("app.adapters.publishing.telegram.httpx.AsyncClient",FakeAsyncClient)
    async with SessionFactory() as session:
        item=await create_manual_artifact(session,kind="TEXT",title="Test",content="Native preview",native={"type":"DICE","emoji":"🎲"})
        await GenericArtifactReviewService(session).approve(item.id)
        pub=await CreateTelegramDraft.execute_for_artifact(session,item,"private-fixture")
        FakeAsyncClient.calls=[]
        result=await ApproveAndPublish(TelegramPublisher(token="test-only")).execute(session,pub.id,artifact=item)
        assert result.status.value=="PUBLISHED"
        assert FakeAsyncClient.calls[0][0].endswith("/sendDice")
        assert FakeAsyncClient.calls[0][1]["json"]["emoji"]=="🎲"
