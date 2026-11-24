from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4
import httpx,pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from app.api.auth import SESSION_COOKIE,issue_token
from app.main import app
from app.application import managed_connections as service
from app.infrastructure.database.models import ManagedConnectionModel,ArtifactModel,PublicationModel,ScheduleItemModel,ScheduleModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_platform_variants import _seed_text_artifact

@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv('NASHR_AUTH_PASSWORD','test-owner');monkeypatch.setenv('NASHR_SESSION_SECRET','test-session-secret');monkeypatch.setenv('NASHR_CONNECTION_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('TELEGRAM_DESTINATION_ID','unchanged-old-target');monkeypatch.setenv('TELEGRAM_BOT_TOKEN','unchanged-old-token')

def browser():
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test',headers={'Origin':'https://test'});client.cookies.set(SESSION_COOKIE,issue_token('owner'));return client

@pytest.mark.asyncio
async def test_write_only_multi_channel_plans_and_separate_history(config,monkeypatch):
    token='123456:'+('A'*30)
    async def check(t,d):
        assert t==token
        return {'destination':d,'bot_id':'123456','bot_username':'test_bot','channel_title':'Synthetic '+d,'can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    async with browser() as client:
        destinations=['-100'+str(uuid4().int)[:12],'-100'+str(uuid4().int)[:12]]
        ids=[]
        for n,d in enumerate(destinations):
            res=await client.post('/api/connections/telegram',json={'label':f'Synthetic {n}','token':token,'destination':d})
            assert res.status_code==200,res.text;assert token not in res.text;ids.append(res.json()['id'])
        overview=await client.get('/api/connections');assert overview.headers['cache-control']=='no-store' and token not in overview.text
        async with SessionFactory() as session:
            row=await session.get(ManagedConnectionModel,UUID(ids[0]));assert row.secret_ciphertext!=token and service.key().decrypt(row.secret_ciphertext.encode()).decode()==token
        uid=await _seed_text_artifact('مادة محلية مستقلة لقناتين')
        assert (await client.post(f'/api/artifacts/{uid}/approve',json={})).status_code==200
        payload={'artifact_ids':[uid],'connection_ids':ids}
        preview=await client.post('/api/connections/telegram/preview',json=payload);assert preview.status_code==200,preview.text
        data=preview.json()['channels'];assert len(data)==2 and all(p['ready_count']==1 for p in data)
        plan_payload={**payload,'name':'قناتان محلياً','timezone':'Asia/Riyadh','start_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'interval_minutes':60,'previews':data}
        saved=await client.post('/api/connections/telegram/plans',json=plan_payload);assert saved.status_code==200,saved.text
        assert len(saved.json()['plans'])==2 and saved.json()['sent_messages']==0 and not saved.json()['activated']
        assert (await client.post('/api/connections/telegram/'+ids[0]+'/remove')).status_code==200
        assert (await client.post('/api/connections/telegram/'+ids[0]+'/state',json={'enabled':True})).status_code==200
        assert (await client.post('/api/connections/telegram/plans',json=plan_payload)).status_code==409
        async with SessionFactory() as session:
            plans=[await session.get(ScheduleModel,UUID(p['id'])) for p in saved.json()['plans']]
            assert {p.telegram_review['destination'] for p in plans}==set(destinations)
            assert {p.telegram_review['connection_id'] for p in plans}==set(ids)
            from app.application.telegram_batch_schedule import reviewed_batch_blocker
            monkeypatch.setenv('TELEGRAM_DESTINATION_ID','changed-environment')
            assert all([await reviewed_batch_blocker(session,p) is None for p in plans])
        histories=[(await client.get('/api/connections/telegram/'+i+'/history')).json() for i in ids]
        assert all(len(h['plans'])==1 and not h['publications'] for h in histories)
        # Publish with a synthetic adapter only. Distinct target histories must
        # neither suppress the second target nor call the real Bot API.
        from app.domain.publications import PublishResult
        calls=[]
        class Fake:
            async def publish(self,**kwargs):
                calls.append(kwargs['destination']);return PublishResult(external_id='test-'+str(len(calls)))
        async def fake_publisher(session,pub):return Fake()
        monkeypatch.setattr(service,'publication_publisher',fake_publisher)
        from app.application.quiz_scheduling import execute_quiz_schedule_item
        for p in plans:
            async with SessionFactory() as session:
                item=await session.scalar(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id==p.id));item_id=item.id
            await execute_quiz_schedule_item(item_id,publisher=Fake())
        assert calls==destinations
        for i in ids:
            history=(await client.get('/api/connections/telegram/'+i+'/history')).json();assert len(history['publications'])==1 and history['publications'][0]['status']=='PUBLISHED'

@pytest.mark.asyncio
async def test_secrets_auth_origin_validation_and_unavailable_key(config,monkeypatch):
    secret='never-echo-me-'+str(uuid4())
    async with browser() as client:
        res=await client.post('/api/connections/telegram',json={'label':'x','token':secret,'destination':'x','extra':secret});assert res.status_code==422 and secret not in res.text
        assert (await client.post('/api/connections/telegram',headers={'Origin':'https://foreign.invalid'},json={'label':'x','token':secret,'destination':'x'})).status_code==403
        monkeypatch.delenv('NASHR_CONNECTION_ENCRYPTION_KEY')
        res=await client.post('/api/connections/telegram',json={'label':'x','token':secret,'destination':'x'});assert res.status_code==409 and secret not in res.text
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
        assert (await client.get('/api/connections')).status_code==401

@pytest.mark.asyncio
async def test_verification_only_calls_read_methods_and_rejects_missing_permissions(config,monkeypatch):
    actual=httpx.AsyncClient;calls=[];allow=False
    def respond(request):
        nonlocal allow
        method=request.url.path.split('/')[-1];calls.append(method)
        if method=='getMe':result={'is_bot':True,'id':123456,'username':'test_bot'}
        elif method=='getChat':result={'id':-100123456,'title':'Synthetic','type':'channel'}
        elif method=='getChatMember':result={'status':'administrator','can_post_messages':allow}
        else:raise AssertionError('unexpected side effect')
        return httpx.Response(200,json={'ok':True,'result':result})
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kw:actual(transport=httpx.MockTransport(respond),**kw))
    token='123456:'+('A'*30)
    with pytest.raises(ValueError):await service.telegram_check(token,'-100123456')
    allow=True;details=await service.telegram_check(token,'-100123456');assert details['destination']=='-100123456'
    assert calls==['getMe','getChat','getChatMember']*2

@pytest.mark.asyncio
async def test_meta_admin_settings_encrypted_and_not_a_user_login(config):
    secret='app-secret-'+str(uuid4())
    async with browser() as client:
        res=await client.post('/api/connections/apps/instagram',json={'app_id':'123456','config_id':'456789','app_secret':secret,'redirect_uri':'https://test/api/connections/instagram/callback','config_reviewed':True})
        assert res.status_code==200,res.text;assert secret not in res.text
        from app.infrastructure.database.models import PlatformAppSettingsModel
        async with SessionFactory() as session:
            row=await session.get(PlatformAppSettingsModel,'instagram');assert secret not in row.ciphertext
            await session.delete(row);await session.commit()

@pytest.mark.asyncio
async def test_unreadable_credentials_never_fall_back_to_old_bot(config,monkeypatch):
    async def check(t,d):return {'destination':d,'bot_id':'123456','bot_username':'test','channel_title':'Synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    async with SessionFactory() as session:
        uid=await service.add_telegram(session,'Synthetic','123456:'+('A'*30),'-100'+str(uuid4().int)[:12])
        row=await session.get(ManagedConnectionModel,UUID(uid));dest=row.details['destination']
        plan=ScheduleModel(name='Synthetic binding',status='DRAFT',timezone='Asia/Riyadh',telegram_review={'connection_id':uid,'destination':dest,'bot_id':'123456'})
        monkeypatch.setenv('NASHR_CONNECTION_ENCRYPTION_KEY',Fernet.generate_key().decode())
        with pytest.raises(ValueError,match='تعذر فتح'):await service.schedule_binding(session,plan)

@pytest.mark.asyncio
async def test_atomic_multichannel_plan_rollback_and_duplicate_channel_rejection(config,monkeypatch):
    async def check(t,d):return {'destination':d,'bot_id':'123456','bot_username':'test','channel_title':'Synthetic','can_post_messages':True}
    monkeypatch.setattr(service,'telegram_check',check)
    uid=await _seed_text_artifact('فحص عدم حفظ نصف خطة')
    destination='-100'+str(uuid4().int)[:12]
    async with browser() as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        channel=(await client.post('/api/connections/telegram',json={'label':'Synthetic','token':'123456:'+('A'*30),'destination':destination})).json()['id']
        assert (await client.post('/api/connections/telegram',json={'label':'Duplicate','token':'123456:'+('B'*30),'destination':destination})).status_code==409
        preview=(await client.post('/api/connections/telegram/preview',json={'artifact_ids':[uid],'connection_ids':[channel]})).json()['channels']
        payload={'artifact_ids':[uid],'connection_ids':[channel,str(uuid4())],'name':'Atomic synthetic','timezone':'Asia/Riyadh','start_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'interval_minutes':60,'previews':preview}
        assert (await client.post('/api/connections/telegram/plans',json=payload)).status_code==409
        history=(await client.get('/api/connections/telegram/'+channel+'/history')).json();assert not history['plans']
        assert (await client.post('/api/connections/telegram/'+channel+'/remove')).status_code==200

@pytest.mark.asyncio
async def test_safe_publisher_does_not_store_token_bearing_exceptions(config,monkeypatch):
    secret='123456:'+('A'*30)
    from app.adapters.publishing.telegram import TelegramPublisher
    async def fail(*args,**kwargs):raise RuntimeError('https://api.telegram.org/bot'+secret+'/sendMessage')
    monkeypatch.setattr(TelegramPublisher,'publish',fail)
    with pytest.raises(RuntimeError) as exc:await service.SafePublisher(secret).publish(destination='synthetic',content='local only')
    assert secret not in str(exc.value)

@pytest.mark.asyncio
async def test_tiktok_summary_reports_connector_not_account_or_execution(config):
    async with browser() as client:
        r=await client.get('/api/connections');assert r.status_code==200
        row=next(x for x in r.json()['platforms'] if x['key']=='tiktok')
        assert row['state']=='IDENTITY_CONNECTION_ONLY'
        assert 'user.info.basic' in row['requirements']
        assert r.json()['execution_authorized'] is False
