import pytest
from sqlalchemy import select,func,delete
from uuid import uuid4
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import PlatformCopyModel,InstagramPlanDraftModel,InstagramExecutionModel,ScheduleModel,PublicationModel,InstagramConnectionModel
from app.application import instagram_plan_review as flow
from tests.integration.test_instagram_execution_core import seed,private_storage
from tests.integration.test_instagram_oauth import config,browser


@pytest.mark.asyncio
async def test_private_preview_draft_repeated_save_and_stale_text(config,monkeypatch):
    uid,_=await seed()
    async with SessionFactory() as s:
        await s.execute(delete(InstagramConnectionModel));await s.commit()
        schedules=await s.scalar(select(func.count()).select_from(ScheduleModel))
        executions=await s.scalar(select(func.count()).select_from(InstagramExecutionModel))
        before=await flow.preview(s,uid)
        assert not before['execution_enabled'] and not before['media_exposure_enabled']
        assert before['account'] is None and before['inspection'] and before['can_save_draft']
        assert before['blockers'] and before['pending'] and before['remaining_steps']
        draft=await flow.save_draft(s,uid,preview_hash=before['preview_hash'])
        assert not draft['stale'] and draft['state']=='DRAFT'
        again=await flow.save_draft(s,uid,preview_hash=before['preview_hash'])
        assert again['id']==draft['id']
        assert await s.scalar(select(func.count()).select_from(ScheduleModel))==schedules
        assert await s.scalar(select(func.count()).select_from(InstagramExecutionModel))==executions
        copy=await s.get(PlatformCopyModel,(uid,'instagram'));copy.fields={**copy.fields,'description':'نص تغير'};await s.commit()
        with pytest.raises(ValueError,match='تغيرت'):await flow.save_draft(s,uid,preview_hash=before['preview_hash'])
        history=await flow.list_drafts(s,uid);assert history['items'][0]['stale']
        assert history['items'][0]['snapshot']['caption']==before['caption']


@pytest.mark.asyncio
async def test_owner_same_origin_and_strict_draft_body(config):
    import httpx
    from app.main import app
    uid,_=await seed();base=f'/api/connections/instagram/materials/{uid}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as anon:
        assert (await anon.post(base+'/preview',json={})).status_code==401
        assert (await anon.get(base+'/drafts')).status_code==401
    async with browser() as c:
        r=await c.post(base+'/preview',json={});assert r.status_code==200,r.text
        assert r.headers['cache-control']=='no-store' and 'app-secret-test' not in r.text
        body={'preview_hash':r.json()['preview_hash'],'share_to_feed':None}
        assert (await c.post(base+'/drafts',json={**body,'authorized':True})).status_code==422
        assert (await c.post(base+'/preview',json={'share_to_feed':'false'})).status_code==422
        assert (await c.post(base+'/preview',headers={'Origin':'https://other.invalid'},json={})).status_code==403
        saved=await c.post(base+'/drafts',json=body);assert saved.status_code==200,saved.text
        assert not saved.json()['execution_enabled']
        assert (await c.get(base+'/drafts')).json()['items']
        assert (await c.post(base+'/preview',json={'share_to_feed':False})).status_code==409


@pytest.mark.asyncio
async def test_current_connection_only_and_no_network_or_media_reads(config,monkeypatch):
    from datetime import datetime,timezone,timedelta
    from app.infrastructure.database.models import InstagramConnectionModel
    from app.application.instagram_oauth import configuration
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    uid,_=await seed()
    def forbidden(*a,**kw):raise AssertionError('No network or storage during preview/save')
    monkeypatch.setattr(S3ArtifactStorage,'from_environment',forbidden)
    async with SessionFactory() as s:
        existing=await s.get(InstagramConnectionModel,1)
        if existing:await s.delete(existing);await s.commit()
        conn=InstagramConnectionModel(id=1,account_id='123',username='selected',token_ciphertext='private-token',scopes=['instagram_basic','instagram_content_publish'],config_hash=configuration()['fingerprint'],connected_at=datetime.now(timezone.utc),enabled=True,last_check_at=datetime.now(timezone.utc),last_check_ok=True)
        s.add(conn);await s.commit()
        p=await flow.preview(s,uid);assert p['account']['username']=='selected'
        assert 'private-token' not in str(p) and 'scopes' not in str(p)
        d=await flow.save_draft(s,uid,preview_hash=p['preview_hash']);assert not d['stale']
        conn.enabled=False;await s.commit()
        with pytest.raises(ValueError):await flow.save_draft(s,uid,preview_hash=p['preview_hash'])
        assert (await flow.list_drafts(s,uid))['items'][0]['stale']
        await s.delete(conn);await s.commit()


@pytest.mark.asyncio
async def test_video_feed_choice_required_for_save(config):
    from app.infrastructure.database.models import ArtifactModel
    from app.application.distribution_readiness import source_fingerprint
    uid,_=await seed()
    async with SessionFactory() as s:
        row=await s.get(ArtifactModel,uid);row.kind='VIDEO';row.mime_type='video/mp4'
        copy=await s.get(PlatformCopyModel,(uid,'instagram'));copy.source_fingerprint=source_fingerprint(row);copy.fields={**copy.fields,'alt_text':''};await s.commit()
        p=await flow.preview(s,uid)
        assert any('Reel' in b for b in p['blockers'])
        with pytest.raises(ValueError):await flow.save_draft(s,uid,preview_hash=p['preview_hash'])
        p=await flow.preview(s,uid,share_to_feed=False)
        draft=await flow.save_draft(s,uid,preview_hash=p['preview_hash'],share_to_feed=False)
        assert draft['snapshot']['share_to_feed'] is False and not draft['execution_enabled']

@pytest.mark.asyncio
async def test_explicit_page_review_pins_identity_without_unified_fallback(config,monkeypatch):
    from datetime import datetime,timezone
    from app.application import instagram_page_oauth as page
    from app.infrastructure.database.models import InstagramPageConnectionModel as PageConnection
    from app.adapters.publishing.instagram_page_login import PageCandidate
    from tests.integration.test_instagram_page_oauth import clear,setup
    await clear();uid,_=await seed()
    async def exchange(code,c):return [PageCandidate('222','page_creator','333','صفحة مختارة',('MANAGE',),'private-page',None)]
    async def facts(c,candidate):return {**candidate.public(),'expires_at':None}
    monkeypatch.setattr(page,'exchange',exchange);monkeypatch.setattr(page,'selected_facts',facts)
    async with browser() as client:
        state=await setup(client);await client.get(page.BASE+'/callback',params={'state':state,'code':'synthetic'});assert (await client.post(page.BASE+'/select',json={'account_id':'222'})).status_code==200
        base=f'/api/connections/instagram/materials/{uid}'
        result=await client.post(base+'/preview',json={'login_mode':'FACEBOOK_PAGE_LOGIN'});assert result.status_code==200,result.text
        p=result.json();assert p['login_mode']=='FACEBOOK_PAGE_LOGIN' and p['account']['account_id']=='222' and p['account']['page_id']=='333'
        assert 'private-page' not in result.text and 'scopes' not in result.text
        assert not p['execution_enabled'] and not p['media_exposure_enabled']
        saved=await client.post(base+'/drafts',json={'login_mode':'FACEBOOK_PAGE_LOGIN','preview_hash':p['preview_hash']});assert saved.status_code==200,saved.text
        assert not saved.json()['stale']
        # Omitting the selected mode never silently saves under another mode.
        assert (await client.post(base+'/drafts',json={'preview_hash':p['preview_hash']})).status_code==409
        async with SessionFactory() as s:
            row=await s.get(PageConnection,1);row.page_name='تغير الاسم';await s.commit()
        assert (await client.get(base+'/drafts')).json()['items'][0]['stale']
        await client.post(page.BASE+'/disconnect')
        p=(await client.post(base+'/preview',json={'login_mode':'FACEBOOK_PAGE_LOGIN'})).json();assert p['account'] is None
        assert (await client.post(base+'/preview',json={'login_mode':'AUTO'})).status_code==422
    await clear()
