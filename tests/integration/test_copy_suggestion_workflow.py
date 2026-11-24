from uuid import UUID
import pytest
from sqlalchemy import select,func
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,CopySuggestionModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_managed_connections import config,browser
from tests.integration.test_platform_variants import _seed_text_artifact
from app.application.copy_suggestions import request_suggestion

class FakeProvider:
    async def suggest(self,**kwargs):return {**kwargs['fields'],'description':'اقتراح اصطناعي للمراجعة فقط'}

@pytest.mark.asyncio
async def test_disabled_live_api_preserves_content_and_creates_no_proposal(config,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key-do-not-use')
    uid=await _seed_text_artifact('أصل لا يستبدل')
    async with browser() as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        before=(await client.get(f'/api/artifacts/{uid}')).json()
        copies=(await client.get(f'/api/artifacts/{uid}/platform-copies')).json()
        copy=next(c for c in copies['items'] if c['platform']=='telegram')
        result=await client.post(f'/api/artifacts/{uid}/platform-copies/telegram/suggestions',json={'version':copy['version'],'current_source_fingerprint':copy['current_source_fingerprint']})
        assert result.status_code==200 and result.json()['state']=='SERVICE_DISABLED'
        assert (await client.get(f'/api/artifacts/{uid}')).json()==before
        assert (await client.get(f'/api/artifacts/{uid}/platform-copies')).json()==copies
        assert result.headers['cache-control']=='no-store'
        blocked=await client.post(f'/api/artifacts/{uid}/platform-copies/telegram/suggestions',headers={'Origin':'https://foreign.invalid'},json={'version':copy['version'],'current_source_fingerprint':copy['current_source_fingerprint']})
        assert blocked.status_code==403
    async with SessionFactory() as s:
        assert (await s.execute(select(func.count()).select_from(CopySuggestionModel).where(CopySuggestionModel.artifact_id==UUID(uid)))).scalar()==0

@pytest.mark.asyncio
async def test_proposal_application_is_explicit_pinned_single_platform_and_one_time(config):
    uid=await _seed_text_artifact('أصل كامل')
    async with browser() as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        before=(await client.get(f'/api/artifacts/{uid}')).json()
        copies=(await client.get(f'/api/artifacts/{uid}/platform-copies')).json()['items'];copy=next(c for c in copies if c['platform']=='telegram')
        async with SessionFactory() as s:
            result=await request_suggestion(s,UUID(uid),'telegram',copy['version'],copy['current_source_fingerprint'],FakeProvider())
        body={'suggestion_id':result['suggestion_id'],'version':copy['version'],'current_source_fingerprint':copy['current_source_fingerprint'],'confirmed':False}
        path=f'/api/artifacts/{uid}/platform-copies/telegram/suggestions/apply'
        assert (await client.post(path,json=body)).status_code==409
        body['confirmed']=True
        applied=await client.post(path,json=body);assert applied.status_code==200,applied.text
        assert applied.json()['fields']['description']=='اقتراح اصطناعي للمراجعة فقط'
        assert (await client.post(path,json=body)).status_code==409
        assert (await client.get(f'/api/artifacts/{uid}')).json()==before
        after=(await client.get(f'/api/artifacts/{uid}/platform-copies')).json()['items']
        assert [c for c in after if c['platform']!='telegram']==[c for c in copies if c['platform']!='telegram']

@pytest.mark.asyncio
async def test_saved_edit_after_proposal_rejects_application(config):
    uid=await _seed_text_artifact('أصل كامل')
    async with browser() as client:
        await client.post(f'/api/artifacts/{uid}/approve',json={})
        copy=next(c for c in (await client.get(f'/api/artifacts/{uid}/platform-copies')).json()['items'] if c['platform']=='telegram')
        async with SessionFactory() as s:result=await request_suggestion(s,UUID(uid),'telegram',1,copy['current_source_fingerprint'],FakeProvider())
        changed={**copy['fields'],'description':'تعديل المستخدم أحدث'}
        assert (await client.patch(f'/api/artifacts/{uid}/platform-copies/telegram',json={'fields':changed,'version':1,'current_source_fingerprint':copy['current_source_fingerprint']})).status_code==200
        body={'suggestion_id':result['suggestion_id'],'version':2,'current_source_fingerprint':copy['current_source_fingerprint'],'confirmed':True}
        assert (await client.post(f'/api/artifacts/{uid}/platform-copies/telegram/suggestions/apply',json=body)).status_code==409
    async with SessionFactory() as s:
        assert (await s.get(PlatformCopyModel,(UUID(uid),'telegram'))).fields==changed
