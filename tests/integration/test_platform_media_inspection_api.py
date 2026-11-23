import io
from uuid import UUID
import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from app.main import app
from app.infrastructure.database.models import ArtifactModel,PublicationModel,ScheduleItemModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_media_scheduling import _media_artifact


@pytest.mark.asyncio
async def test_private_probe_is_bounded_read_only_and_rejects_stale_original(monkeypatch):
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    uid=str(await _media_artifact(review_status='DRAFT',caption='وصف أصلي'))
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,UUID(uid));row.kind='IMAGE';row.content=None;row.mime_type='image/jpeg';row.storage_uri='s3://synthetic/artifacts/probe.jpg';row.artifact_metadata={'source_type':'MEDIA_BANK_UPLOAD','caption':'وصف أصلي'};context=dict(row.resolved_context);contract=dict(context['output_contract']);definition=dict(contract['definition']);definition['mime_type']='image/jpeg';contract['definition']=definition;context['output_contract']=contract;row.resolved_context=context;await session.commit()
    data=io.BytesIO();Image.new('RGB',(640,800)).save(data,format='JPEG')
    class Storage:
        async def get_bytes(self,uri,*,max_bytes):
            assert uri=='s3://synthetic/artifacts/probe.jpg' and max_bytes==50*1024*1024
            return data.getvalue()
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:Storage())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        approved=await client.post(f'/api/artifacts/{uid}/approve',json={});assert approved.status_code==200,approved.text
        result=await client.post(f'/api/artifacts/{uid}/platform-copies/instagram/inspect-media',json={})
        assert result.status_code==200,result.text
        probe=result.json();assert probe['measurements']['width']==640 and not probe['execution_authorized'] and probe['pending']
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,UUID(uid));assert row.content is None and row.artifact_metadata=={'source_type':'MEDIA_BANK_UPLOAD','caption':'وصف أصلي'}
            assert not (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id==row.id))).scalars().all()
            assert not (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.artifact_id==row.id))).scalars().all()
            row.artifact_metadata={'caption':'تغير الأصل'};await session.commit()
        assert (await client.post(f'/api/artifacts/{uid}/platform-copies/instagram/inspect-media',json={})).status_code==409
