from uuid import UUID
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import select,func,delete
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramConnectionModel,InstagramPlanDraftModel,ScheduleModel
from app.application.instagram_oauth import configuration
from app.application import instagram_plan_review as review
from tests.integration.test_instagram_execution_core import seed,private_storage
from tests.integration.test_instagram_oauth import config,browser
from tests.integration.instagram_plan_simulation import simulate_due_review

async def connected(s):
    await s.execute(delete(InstagramConnectionModel))
    now=datetime.now(timezone.utc)
    s.add(InstagramConnectionModel(id=1,account_id='100',username='synthetic_account',token_ciphertext='never-opened',scopes=[],config_hash=configuration()['fingerprint'],connected_at=now,enabled=True,last_check_at=now,last_check_ok=True))
    await s.commit()

@pytest.mark.asyncio
async def test_time_roundtrip_hash_elapsed_and_no_schedule(config):
    uid,_=await seed();at=(datetime.now(timezone.utc)+timedelta(days=1)).astimezone(timezone(timedelta(hours=3)))
    async with SessionFactory() as s:
        count=await s.scalar(select(func.count()).select_from(ScheduleModel))
        p=await review.preview(s,uid,planned_at=at,timezone_name='Asia/Riyadh')
        assert p['timing_intent']['local_time']==at.isoformat() and not p['timing_intent']['scheduled']
        d=await review.save_draft(s,uid,preview_hash=p['preview_hash'],planned_at=at,timezone_name='Asia/Riyadh')
        assert not d['stale'] and not d['timing_elapsed']
        with pytest.raises(ValueError):await review.save_draft(s,uid,preview_hash=p['preview_hash'],planned_at=at+timedelta(minutes=1),timezone_name='Asia/Riyadh')
        assert await s.scalar(select(func.count()).select_from(ScheduleModel))==count
        for bad,zone in [(at.replace(tzinfo=None),'Asia/Riyadh'),(at,'bad/timezone'),(at,'UTC'),(None,'Asia/Riyadh')]:
            with pytest.raises(ValueError):await review.preview(s,uid,planned_at=bad,timezone_name=zone)
        past=at-timedelta(days=2);p=await review.preview(s,uid,planned_at=past,timezone_name='Asia/Riyadh')
        with pytest.raises(ValueError,match='مضى'):await review.save_draft(s,uid,preview_hash=p['preview_hash'],planned_at=past,timezone_name='Asia/Riyadh')
        record=await s.get(InstagramPlanDraftModel,UUID(d['id']));record.snapshot={**record.snapshot,'timing_intent':{**p['timing_intent']}};await s.commit()
        assert (await review.describe_draft(s,record))['timing_elapsed']

@pytest.mark.asyncio
@pytest.mark.parametrize('outcome,state,calls',[('success','PUBLISHED',['create','publish','reconcile']),('create_unknown','CREATE_UNKNOWN',['create']),('publish_unknown','PUBLISHED_ID_UNKNOWN',['create','publish','status'])])
async def test_review_to_due_synthetic_execution(config,outcome,state,calls):
    uid,_=await seed();at=datetime.now(timezone.utc)+timedelta(days=1)
    async with SessionFactory() as s:
        await connected(s)
        p=await review.preview(s,uid,planned_at=at,timezone_name='UTC')
        assert not p['blockers']
        d=await review.save_draft(s,uid,preview_hash=p['preview_hash'],planned_at=at,timezone_name='UTC')
        with pytest.raises(ValueError):await simulate_due_review(s,d['id'],reviewed_hash=p['preview_hash'],due_at=at-timedelta(seconds=1))
        with pytest.raises(ValueError):await simulate_due_review(s,d['id'],reviewed_hash='0'*64,due_at=at)
        result=await simulate_due_review(s,d['id'],reviewed_hash=p['preview_hash'],due_at=at,outcome=outcome)
        assert result['state']==state and result['calls']==calls and result['external_requests']==0 and not result['media_exposed']
        assert not result['owner_approval_recorded']
        with pytest.raises(ValueError):await simulate_due_review(s,d['id'],reviewed_hash=p['preview_hash'],due_at=at,outcome=outcome)
        await s.execute(delete(InstagramConnectionModel));await s.commit()

@pytest.mark.asyncio
async def test_api_timing_is_preparation_only(config):
    uid,_=await seed();at=datetime.now(timezone.utc)+timedelta(days=1)
    async with browser() as c:
        base=f'/api/connections/instagram/materials/{uid}'
        body={'planned_at':at.isoformat(),'timezone_name':'UTC'}
        p=await c.post(base+'/preview',json=body);assert p.status_code==200,p.text
        assert not p.json()['timing_intent']['scheduled']
        saved=await c.post(base+'/drafts',json={**body,'preview_hash':p.json()['preview_hash']});assert saved.status_code==200,saved.text
        assert not saved.json()['execution_enabled']
        assert (await c.post(base+'/drafts',json={**body,'preview_hash':p.json()['preview_hash'],'approved':True})).status_code==422
        assert (await c.post(base+'/execute',json={})).status_code in {404,405}

@pytest.mark.asyncio
async def test_local_cancel_retains_history_and_cannot_affect_other_material(config):
    uid,_=await seed();other,_=await seed()
    async with SessionFactory() as s:
        p=await review.preview(s,uid);d=await review.save_draft(s,uid,preview_hash=p['preview_hash'])
        with pytest.raises(ValueError):await review.cancel_review_draft(s,other,UUID(d['id']))
        cancelled=await review.cancel_review_draft(s,uid,UUID(d['id']))
        assert cancelled['state']=='CANCELLED' and not cancelled['remote_changed']
        assert (await review.cancel_review_draft(s,uid,UUID(d['id'])))==cancelled
        assert (await review.list_drafts(s,uid))['items'][0]['state']=='CANCELLED'
        new=await review.save_draft(s,uid,preview_hash=p['preview_hash']);assert new['id']!=d['id']
    async with browser() as c:
        assert (await c.post(f'/api/connections/instagram/materials/{uid}/drafts/{d["id"]}/cancel',headers={'Origin':'https://evil.invalid'})).status_code==403
        assert (await c.post(f'/api/connections/instagram/materials/{uid}/drafts/{d["id"]}/cancel')).status_code==200


@pytest.mark.asyncio
async def test_pre_timing_snapshot_stays_valid(config):
    uid,_=await seed()
    async with SessionFactory() as s:
        p=await review.preview(s,uid);p.pop('timing_intent');p['preview_hash']=review.fingerprint({k:v for k,v in p.items() if k not in {'preview_hash','can_save_draft','caveat'}})
        record=InstagramPlanDraftModel(artifact_id=uid,snapshot_hash=p['preview_hash'],snapshot=p,state='DRAFT');s.add(record);await s.commit()
        assert not (await review.describe_draft(s,record))['stale']
