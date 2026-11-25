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
        for copy in data['items']:
            assert copy['execution_status'] == 'NOT_AUTHORIZED'
            assert 'لا يربط حساباً' in copy['execution_blockers'][0]
            assert 'مسار المنصة المنفصل' in copy['execution_blockers'][0]
            assert 'لا موصل نشر' not in copy['execution_blockers'][0]
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
        from unittest.mock import patch
        with patch.dict('os.environ', {'TELEGRAM_DESTINATION_ID':'synthetic-only'}):
            blocked=await client.post(f'/api/artifacts/{uid}/telegram-media-draft',json={})
            assert blocked.status_code==409 and 'نسخة Telegram' in blocked.json()['detail']
            inline=await client.post(f'/api/artifacts/{uid}/telegram-draft',json={})
            assert inline.status_code==409 and 'نسخة Telegram' in inline.json()['detail']
            from datetime import datetime,timedelta,timezone
            scheduled=await client.post(f'/api/artifacts/{uid}/schedule',json={'name':'لا يختار الأصل بصمت','timezone':'Asia/Riyadh','scheduled_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
            assert scheduled.status_code==409 and 'نسخة Telegram' in scheduled.json()['detail']
        selected=await client.post('/api/artifacts/distribution-selection',json={'artifact_ids':[uid],'platforms':['telegram'],'fingerprints':{uid:telegram['current_source_fingerprint']}})
        assert selected.status_code==200
        selected_telegram=next(target for target in selected.json()['items'][0]['targets'] if target['platform']=='telegram')
        assert selected_telegram['copy_status']=='FIELDS_VALIDATED' and selected_telegram['copy_version']==2

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

@pytest.mark.asyncio
async def test_batch_prepares_only_missing_copies_and_rolls_back_invalid_selection():
    from sqlalchemy import delete
    ids=[await _seed_text_artifact('مادة أولى'),await _seed_text_artifact('مادة ثانية')]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for uid in ids:
            await client.post(f'/api/artifacts/{uid}/approve',json={})
        async with SessionFactory() as session:
            await session.execute(delete(PlatformCopyModel).where(PlatformCopyModel.artifact_id.in_([UUID(uid) for uid in ids])))
            await session.commit()
        invalid=await _seed_text_artifact('غير معتمدة')
        failed=await client.post('/api/artifacts/platform-copies/prepare-batch',json={'artifact_ids':[ids[0],invalid]})
        assert failed.status_code==422
        assert (await client.get(f'/api/artifacts/{ids[0]}/platform-copies')).json()['items']==[]
        first=await client.post('/api/artifacts/platform-copies/prepare-batch',json={'artifact_ids':ids})
        assert first.status_code==200 and first.json()['prepared']==2
        data=first.json()['items'][0]
        telegram=next(copy for copy in data['items'] if copy['platform']=='telegram')
        fields={**telegram['fields'],'description':'تعديل محفوظ'}
        await client.patch(f"/api/artifacts/{data['artifact_id']}/platform-copies/telegram",json={'fields':fields,'version':telegram['version'],'current_source_fingerprint':telegram['current_source_fingerprint']})
        second=(await client.post('/api/artifacts/platform-copies/prepare-batch',json={'artifact_ids':ids})).json()
        changed=next(row for row in second['items'] if row['artifact_id']==data['artifact_id'])
        assert next(copy for copy in changed['items'] if copy['platform']=='telegram')['fields']['description']=='تعديل محفوظ'
        assert second['selection_changed'] is False and second['publications_created']==0 and second['schedules_created']==0
