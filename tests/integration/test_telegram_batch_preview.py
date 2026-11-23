from uuid import UUID,uuid4
import httpx
import pytest
from app.main import app
from app.infrastructure.database.models import ArtifactModel,DistributionSelectionModel,PublicationModel
from app.infrastructure.database.session import SessionFactory
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
async def test_batch_preview_respects_selection_prior_publication_and_never_writes(monkeypatch):
    monkeypatch.setenv('TELEGRAM_DESTINATION_ID','synthetic-target')
    ids=[await _seed_text_artifact('أول'),await _seed_text_artifact('ثان'),await _seed_text_artifact('ثالث')]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for uid in ids:
            await client.post(f'/api/artifacts/{uid}/approve',json={})
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,UUID(ids[1]))
            session.add(DistributionSelectionModel(artifact_id=row.id,platforms=[],source_fingerprint=source_fingerprint(row)))
            third=await session.get(ArtifactModel,UUID(ids[2]))
            session.add(PublicationModel(artifact_id=third.id,knowledge_unit_id=third.source_knowledge_unit_id,platform='telegram',destination='synthetic-target',content=third.content,status='PUBLISHED',external_id='test-only'))
            await session.commit()
        for _ in range(2):
            response=await client.post('/api/artifacts/telegram-batch-preview',json={'artifact_ids':ids})
            assert response.status_code==200,response.text
            body=response.json()
            assert body['destination']=='synthetic-target'
            assert body['ready_count']==1 and body['blocked_count']==2
            assert body['items'][0]['ready'] is True
            assert 'مستبعد' in ' '.join(body['items'][1]['blockers'])
            assert body['items'][2]['publications'][0]['external_ids']==['test-only']
            assert body['read_only'] is True and body['execution_authorized'] is False
        assert (await client.post('/api/artifacts/telegram-batch-preview',json={'artifact_ids':[ids[0],ids[0]]})).status_code==422
        missing=(await client.post('/api/artifacts/telegram-batch-preview',json={'artifact_ids':[str(uuid4())]})).json()
        assert missing['blocked_count']==1

@pytest.mark.asyncio
async def test_batch_schedule_is_draft_atomic_and_detects_repeats(monkeypatch):
    from datetime import datetime,timedelta,timezone
    from app.infrastructure.database.models import ScheduleModel,ScheduleItemModel
    from sqlalchemy import select
    monkeypatch.setenv('TELEGRAM_DESTINATION_ID','synthetic-target')
    uid=await _seed_text_artifact('دفعة بمراجعة مستقلة')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        preview=(await client.post('/api/artifacts/telegram-batch-preview',json={'artifact_ids':[uid]})).json()
        payload={'artifact_ids':[uid],'name':'اختبار محلي','timezone':'Asia/Riyadh','start_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'interval_minutes':60,'destination':'synthetic-target','fingerprints':{uid:'stale'}}
        assert (await client.post('/api/artifacts/telegram-batch-schedule',json=payload)).status_code==422
        payload['fingerprints']={uid:preview['items'][0]['source_fingerprint']}
        payload['copy_versions']={uid:preview['items'][0].get('copy_version')}
        first=await client.post('/api/artifacts/telegram-batch-schedule',json=payload)
        assert first.status_code==201,first.text
        assert first.json()['status']=='DRAFT'
        assert (await client.post('/api/artifacts/telegram-batch-schedule',json=payload)).status_code==422
        async with SessionFactory() as session:
            schedule=await session.get(ScheduleModel,UUID(first.json()['id']))
            assert schedule.status=='DRAFT'
            rows=(await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id==schedule.id))).scalars().all()
            assert len(rows)==1 and rows[0].attempts==0 and rows[0].status=='PENDING'
            from app.application.telegram_batch_schedule import reviewed_batch_blocker
            assert await reviewed_batch_blocker(session,schedule) is None
            from app.application.scheduling import _execute_claimed_item
            rows[0].status='PROCESSING'
            await session.commit()
            monkeypatch.setenv('TELEGRAM_DESTINATION_ID','changed-target')
            await _execute_claimed_item(rows[0].id, publisher=object())
            await session.refresh(rows[0])
            assert rows[0].status=='FAILED' and 'وجهة' in rows[0].last_error

            assert 'وجهة' in await reviewed_batch_blocker(session,schedule)
            monkeypatch.setenv('TELEGRAM_DESTINATION_ID','synthetic-target')
            artifact=await session.get(ArtifactModel,UUID(uid))
            artifact.content='نص تغير بعد المراجعة'
            await session.flush()
            assert 'محتوى' in await reviewed_batch_blocker(session,schedule)
