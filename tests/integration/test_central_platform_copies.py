from uuid import UUID
import httpx
import pytest
from sqlalchemy import select
from app.main import app
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,PublicationModel,ScheduleItemModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_platform_variants import _seed_text_artifact

@pytest.mark.asyncio
async def test_copies_prepare_on_approval_preserve_edits_and_enforce_version_and_source():
    uid=await _seed_text_artifact('نص كامل لا يُقص')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.post(f'/api/artifacts/{uid}/approve',json={})).status_code==200
        data=(await client.get(f'/api/artifacts/{uid}/platform-copies')).json()
        assert len(data['items'])==6
        original={row['platform']:row for row in data['items']}
        assert original['telegram']['fields']['description']=='نص كامل لا يُقص'
        youtube=original['youtube']
        assert youtube['field_status']=='BLOCKED'
        assert youtube['sources'][0].startswith('https://developers.google.com/')
        telegram=original['telegram']
        payload={'fields':{**telegram['fields'],'description':'نسخة معدلة دون تغيير الأصل'},'version':1,'current_source_fingerprint':telegram['current_source_fingerprint']}
        changed=await client.patch(f'/api/artifacts/{uid}/platform-copies/telegram',json=payload)
        assert changed.status_code==200,changed.text
        assert changed.json()['origin']=='USER_EDITED'
        assert (await client.patch(f'/api/artifacts/{uid}/platform-copies/telegram',json=payload)).status_code==409
        reprepare=(await client.post(f'/api/artifacts/{uid}/platform-copies/prepare',json={})).json()
        result={row['platform']:row for row in reprepare['items']}
        assert result['telegram']['fields']['description']=='نسخة معدلة دون تغيير الأصل'
        assert result['youtube']['fields']==youtube['fields']
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,UUID(uid))
            assert row.review_status=='APPROVED' and row.content=='نص كامل لا يُقص'
            assert not (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id==row.id))).scalars().all()
            assert not (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.artifact_id==row.id))).scalars().all()
            row.content='تغير الأصل لاحقاً'
            await session.commit()
        stale=(await client.get(f'/api/artifacts/{uid}/platform-copies')).json()['items']
        assert all(copy['source_stale'] and copy['field_status']=='BLOCKED' for copy in stale)

@pytest.mark.asyncio
async def test_reviewed_telegram_copy_runs_only_from_new_pinned_batch(monkeypatch):
    from datetime import datetime,timedelta,timezone
    from app.application.scheduling import _execute_claimed_item
    from app.adapters.publishing.fake import FakePublisher
    monkeypatch.setenv('TELEGRAM_DESTINATION_ID','synthetic-test')
    uid=await _seed_text_artifact('الأصل المعتمد')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        copies=(await client.get(f'/api/artifacts/{uid}/platform-copies')).json()['items']
        copy=next(item for item in copies if item['platform']=='telegram')
        payload={'fields':{**copy['fields'],'description':'نسخة Telegram المعدلة'},'version':copy['version'],'current_source_fingerprint':copy['current_source_fingerprint']}
        assert (await client.patch(f'/api/artifacts/{uid}/platform-copies/telegram',json=payload)).status_code==200
        item=(await client.post('/api/artifacts/telegram-batch-preview',json={'artifact_ids':[uid]})).json()['items'][0]
        assert item['content']=='نسخة Telegram المعدلة' and item['copy_version']==2
        plan={'artifact_ids':[uid],'fingerprints':{uid:item['source_fingerprint']},'copy_versions':{uid:2},'name':'خطة اختبار نسخة','timezone':'Asia/Riyadh','destination':'synthetic-test','start_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'interval_minutes':60}
        response=await client.post('/api/artifacts/telegram-batch-schedule',json=plan)
        assert response.status_code==201,response.text
        async with SessionFactory() as session:
            scheduled=(await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id==UUID(response.json()['id'])))).scalar_one()
            scheduled.status='PROCESSING'
            await session.commit()
            item_id=scheduled.id
        class Capture(FakePublisher):
            seen=None
            async def publish(self,**kwargs):
                self.seen=kwargs['content']
                return await super().publish(**kwargs)
        publisher=Capture()
        await _execute_claimed_item(item_id,publisher=publisher)
        assert publisher.seen=='نسخة Telegram المعدلة'
        async with SessionFactory() as session:
            assert (await session.get(ArtifactModel,UUID(uid))).content=='الأصل المعتمد'
