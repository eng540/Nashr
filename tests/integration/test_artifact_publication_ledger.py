from datetime import datetime,timezone
from uuid import UUID,uuid4
import httpx
import pytest
from sqlalchemy import select,func
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import PublicationModel,ScheduleModel,ScheduleItemModel
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
async def test_ledger_reads_all_ids_destination_and_attempts_without_mutation():
    uid=await _seed_text_artifact('سجل اختبار اصطناعي')
    now=datetime.now(timezone.utc)
    async with SessionFactory() as session:
        from app.infrastructure.database.models import ArtifactModel
        artifact=await session.get(ArtifactModel,UUID(uid))
        pub=PublicationModel(knowledge_unit_id=artifact.source_knowledge_unit_id,artifact_id=artifact.id,platform='telegram',destination='synthetic-private-channel',content='snapshot',status='PUBLISHED',external_id='first',external_ids=['first','second'],published_at=now)
        session.add(pub);await session.flush()
        schedule=ScheduleModel(name='synthetic test',status='COMPLETED',timezone='Asia/Riyadh')
        session.add(schedule);await session.flush()
        session.add(ScheduleItemModel(schedule_id=schedule.id,artifact_id=artifact.id,publication_id=pub.id,position=1,scheduled_at=now,status='PUBLISHED',attempts=1))
        await session.commit()
        count=(await session.execute(select(func.count()).select_from(PublicationModel))).scalar_one()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for _ in range(2):
            response=await client.get(f'/api/artifacts/{uid}/publications')
            assert response.status_code==200,response.text
            payload=response.json();assert payload['total']==1
            row=payload['items'][0]
            assert row['destination']=='synthetic-private-channel'
            assert row['external_ids']==['first','second']
            assert row['schedules'][0]['attempts']==1
            assert row['content']=='snapshot'
        missing=await client.get(f'/api/artifacts/{uuid4()}/publications')
        assert missing.status_code==404
    async with SessionFactory() as session:
        assert (await session.execute(select(func.count()).select_from(PublicationModel))).scalar_one()==count


@pytest.mark.asyncio
async def test_empty_ledger_never_creates_draft_and_bounds_pagination():
    uid=await _seed_text_artifact('لا منشور')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get(f'/api/artifacts/{uid}/publications')
        assert response.json()['items']==[]
        assert response.json()['total']==0
        for query in ['limit=101','offset=-1','limit=0']:
            assert (await client.get(f'/api/artifacts/{uid}/publications?{query}')).status_code==422
