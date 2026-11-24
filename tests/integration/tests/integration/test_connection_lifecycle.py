"""Synthetic-only lifecycle contracts. Never talks to the real Bot API."""
from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select,delete
from tests.integration.test_managed_connections import config,browser
from tests.integration.test_platform_variants import _seed_text_artifact
from app.application import managed_connections as service
from app.infrastructure.database.models import ManagedConnectionModel as Connection,LegacyTelegramBindingModel as Legacy,ScheduleModel,PublicationModel,ScheduleItemModel
from app.infrastructure.database.session import SessionFactory

@pytest.fixture
async def legacy_clean():
    async with SessionFactory() as session:
        processing=(await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.status=='PROCESSING'))).scalars().all()
        ids=[item.id for item in processing]
        for item in processing:item.status='FAILED'
        await session.execute(delete(Legacy));await session.commit()
    yield
    async with SessionFactory() as session:
        for uid in ids:
            item=await session.get(ScheduleItemModel,uid)
            if item:item.status='PROCESSING'
        await session.execute(delete(Legacy));await session.commit()

@pytest.mark.asyncio
async def test_legacy_import_preserves_address_payload_time_and_runtime(config,monkeypatch,legacy_clean):
    token='123456:'+('A'*30);dest='@synthetic_old';canonical='-100'+str(uuid4().int)[:12]
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN',token);monkeypatch.setenv('TELEGRAM_DESTINATION_ID',dest)
    calls=[]
    async def check(t,d):
        calls.append((t,d));return {'destination':canonical,'bot_id':'123456','channel_title':'Synthetic','bot_username':'synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    async with SessionFactory() as session:
        # No reactivation or content mutation by import.
        plan=ScheduleModel(name='Legacy synthetic',status='PAUSED',timezone='Asia/Riyadh',telegram_review={'destination':dest,'fingerprints':{}})
        session.add(plan);await session.commit();plan_id=plan.id
    async with browser() as client:
        response=await client.post('/api/connections/telegram/import-legacy');assert response.status_code==200,response.text
        uid=response.json()['id'];assert token not in response.text
        assert response.json()['sent_messages']==0
        monkeypatch.delenv('TELEGRAM_BOT_TOKEN');monkeypatch.setenv('TELEGRAM_DESTINATION_ID','-100other')
        assert (await client.post('/api/connections/telegram/import-legacy')).json()['already_imported']
        assert len(calls)==1
        async with SessionFactory() as session:
            assert await service.default_binding(session)==(dest,UUID(uid))
            plan=await session.get(ScheduleModel,plan_id)
            assert plan.status=='PAUSED' and plan.telegram_review['destination']==dest
            assert plan.telegram_review['connection_id']==uid and plan.telegram_review['fingerprints']=={}
            destination,publisher=await service.schedule_binding(session,plan);assert destination==dest
            row=await session.get(Connection,UUID(uid));assert token not in row.secret_ciphertext
        assert (await client.post('/api/connections/telegram/'+uid+'/state',json={'enabled':False})).status_code==200
        assert (await client.get('/api/connections/telegram/'+uid+'/history')).status_code==200
        async with SessionFactory() as session:
            with pytest.raises(ValueError,match='معطلة'):await service.default_binding(session)
            plan=await session.get(ScheduleModel,plan_id)
            with pytest.raises(ValueError,match='معطلة'):await service.schedule_binding(session,plan)
        assert (await client.post('/api/connections/telegram/'+uid+'/state',json={'enabled':True})).status_code==200

@pytest.mark.asyncio
async def test_rotation_rejects_different_bot_preserves_disabled_state_and_history(config,monkeypatch):
    first='123456:'+('A'*30);updated='123456:'+('B'*30);different='999999:'+('C'*30)
    dest='-100'+str(uuid4().int)[:12]
    async def check(t,d):return {'destination':d,'bot_id':t.split(':')[0],'channel_title':'Synthetic','bot_username':'synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    async with SessionFactory() as session:uid=await service.add_telegram(session,'Rotation synthetic',first,dest)
    async with browser() as client:
        assert (await client.post('/api/connections/telegram/'+uid+'/state',json={'enabled':False})).status_code==200
        res=await client.post('/api/connections/telegram/'+uid+'/token',json={'token':different});assert res.status_code==409 and different not in res.text
        res=await client.post('/api/connections/telegram/'+uid+'/token',json={'token':updated});assert res.status_code==200 and not res.json()['enabled'] and updated not in res.text
        async with SessionFactory() as session:
            row,token=await service.selected(session,uid,allow_disabled=True);assert token==updated and row.details['bot_id']=='123456' and row.details['destination']==dest
        monkeypatch.setenv('NASHR_CONNECTION_ENCRYPTION_KEY',Fernet.generate_key().decode())
        assert (await client.get('/api/connections/telegram/'+uid+'/history')).status_code==200
        assert (await client.post('/api/connections/telegram/'+uid+'/state',json={'enabled':False})).status_code==200
        assert (await client.post('/api/connections/telegram/'+uid+'/state',json={'enabled':True})).status_code==409

@pytest.mark.asyncio
async def test_disable_stops_preview_and_execution_without_adapter_call(config,monkeypatch):
    dest='-100'+str(uuid4().int)[:12]
    async def check(t,d):return {'destination':d,'bot_id':'123456','channel_title':'Synthetic','bot_username':'synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    uid=await _seed_text_artifact('اختبار تعطيل محلي دون إرسال')
    async with browser() as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        cid=(await client.post('/api/connections/telegram',json={'label':'Disable synthetic','token':'123456:'+('A'*30),'destination':dest})).json()['id']
        preview=(await client.post('/api/connections/telegram/preview',json={'artifact_ids':[uid],'connection_ids':[cid]})).json()['channels']
        payload={'artifact_ids':[uid],'connection_ids':[cid],'previews':preview,'name':'Disabled plan','timezone':'Asia/Riyadh','start_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'interval_minutes':60}
        result=await client.post('/api/connections/telegram/plans',json=payload);assert result.status_code==200,result.text
        plan_id=UUID(result.json()['plans'][0]['id'])
        assert (await client.post('/api/connections/telegram/'+cid+'/state',json={'enabled':False})).status_code==200
        assert (await client.post('/api/connections/telegram/preview',json={'artifact_ids':[uid],'connection_ids':[cid]})).status_code==409
        async with SessionFactory() as session:item=await session.scalar(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id==plan_id));item_id=item.id
        from app.application.quiz_scheduling import execute_quiz_schedule_item
        class Never:
            async def publish(self,**kw):raise AssertionError('must not reach adapter')
        await execute_quiz_schedule_item(item_id,publisher=Never())
        async with SessionFactory() as session:
            item=await session.get(ScheduleItemModel,item_id);assert item.status=='FAILED' and 'معطلة' in item.last_error
        assert (await client.post('/api/connections/telegram/'+cid+'/remove')).json()['history_preserved']
        history=(await client.get('/api/connections/telegram/'+cid+'/history')).json();assert any(p['id']==str(plan_id) for p in history['plans'])

@pytest.mark.asyncio
async def test_verification_failure_keeps_secret_and_reports_latest_check(config,monkeypatch):
    async def check(t,d):return {'destination':d,'bot_id':'123456','channel_title':'Synthetic','bot_username':'synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    async with SessionFactory() as session:
        uid=await service.add_telegram(session,'Verify synthetic','123456:'+('A'*30),'-100'+str(uuid4().int)[:12]);row=await session.get(Connection,UUID(uid));cipher=row.secret_ciphertext
    async def fail(t,d):raise ValueError('synthetic denied')
    monkeypatch.setattr(service,'telegram_check',fail)
    async with browser() as client:
        assert (await client.post('/api/connections/telegram/'+uid+'/verify')).status_code==409
        assert (await client.post('/api/connections/telegram/'+uid+'/state',json={'enabled':True})).status_code==409
        data=(await client.get('/api/connections')).json();item=next(i for i in data['telegram']['items'] if i['id']==uid);assert item['last_check_ok'] is False
    async with SessionFactory() as session:row=await session.get(Connection,UUID(uid));assert row.secret_ciphertext==cipher

@pytest.mark.asyncio
async def test_pending_publication_blocks_disable_and_rotation(config,monkeypatch):
    async def check(t,d):return {'destination':d,'bot_id':'123456','channel_title':'Synthetic','bot_username':'synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    uid=await _seed_text_artifact('سجل غير محسوم يحجب تغيير الربط')
    from app.application.artifacts import load_artifact
    from app.application.publications import CreateTelegramDraft
    async with SessionFactory() as session:
        cid=await service.add_telegram(session,'Pending synthetic','123456:'+('A'*30),'-100'+str(uuid4().int)[:12]);row=await session.get(Connection,UUID(cid));artifact=await load_artifact(session,UUID(uid))
        draft=await CreateTelegramDraft.execute_for_artifact(session,artifact,row.details['destination'],connection_id=UUID(cid))
        pub=await session.get(PublicationModel,draft.id);pub.status='PUBLISHING';await session.commit()
    async with browser() as client:
        assert (await client.post('/api/connections/telegram/'+cid+'/state',json={'enabled':False})).status_code==409
        assert (await client.post('/api/connections/telegram/'+cid+'/token',json={'token':'123456:'+('B'*30)})).status_code==409
    async with SessionFactory() as session:
        row,token=await service.selected(session,cid);assert row.enabled and token=='123456:'+('A'*30)

@pytest.mark.asyncio
async def test_import_keeps_published_payload_ids_and_blocks_alias_republication(config,monkeypatch,legacy_clean):
    token='123456:'+('A'*30);dest='@synthetic_old';canonical='-100'+str(uuid4().int)[:12]
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN',token);monkeypatch.setenv('TELEGRAM_DESTINATION_ID',dest)
    async def check(t,d):return {'destination':canonical,'bot_id':'123456','channel_title':'Synthetic','bot_username':'synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    uid=await _seed_text_artifact('مادة منشورة لا تعاد بعد استيراد العنوان')
    from app.application.artifacts import load_artifact
    from app.application.publications import CreateTelegramDraft
    at=datetime.now(timezone.utc)-timedelta(days=1)
    async with SessionFactory() as session:
        artifact=await load_artifact(session,UUID(uid));draft=await CreateTelegramDraft.execute_for_artifact(session,artifact,dest)
        pub=await session.get(PublicationModel,draft.id);pub.status='PUBLISHED';pub.content='unchanged historic content';pub.external_id='517';pub.external_ids=['517','518'];pub.published_at=at
        plan=ScheduleModel(name='Legacy preserved items',status='PAUSED',timezone='Asia/Riyadh');session.add(plan);await session.flush()
        item=ScheduleItemModel(schedule_id=plan.id,artifact_id=UUID(uid),position=1,status='PENDING',scheduled_at=at+timedelta(days=5));session.add(item);await session.commit();item_id=item.id;item_at=item.scheduled_at;plan_id=plan.id
    async with browser() as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        result=await client.post('/api/connections/telegram/import-legacy');assert result.status_code==200,result.text
        cid=result.json()['id']
        log=(await client.get('/api/connections/telegram/'+cid+'/history')).json();assert any(p['id']==str(draft.id) for p in log['publications'])
        preview=await client.post('/api/connections/telegram/preview',json={'artifact_ids':[uid],'connection_ids':[cid]});assert preview.status_code==200
        assert preview.json()['channels'][0]['blocked_count']==1
    async with SessionFactory() as session:
        pub=await session.get(PublicationModel,draft.id);assert pub.content=='unchanged historic content' and pub.external_id=='517' and pub.external_ids==['517','518'] and pub.published_at==at and pub.destination==dest and str(pub.connection_id)==cid
        item=await session.get(ScheduleItemModel,item_id);assert item.status=='PENDING' and item.scheduled_at==item_at
        plan=await session.get(ScheduleModel,plan_id);assert plan.status=='PAUSED' and plan.telegram_review['destination']==dest
        artifact=await load_artifact(session,UUID(uid));same=await CreateTelegramDraft.execute_for_artifact(session,artifact,canonical,connection_id=UUID(cid));assert same.id==draft.id
        publisher=await service.publication_publisher(session,pub)
        async def fake(**kw):assert kw['destination']==canonical;return 'read only synthetic call'
        publisher.inner.publish=fake
        assert await publisher.publish(destination=dest,content='synthetic only')=='read only synthetic call'
