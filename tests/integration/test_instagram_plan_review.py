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
