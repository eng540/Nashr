import os
from uuid import UUID
import httpx
import pytest
from sqlalchemy import func, select
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel, PublicationModel, ScheduleModel
from app.application.distribution_readiness import source_fingerprint
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
async def test_unchanged_fallback_inherits_approval_and_never_cuts_or_creates_publications():
    uid = await _seed_text_artifact('كلمة ' * 1000)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        await client.post(f'/api/artifacts/{uid}/approve', json={})
        async with SessionFactory() as session:
            before = [(await session.execute(select(func.count()).select_from(model))).scalar_one() for model in [PublicationModel, ScheduleModel]]
        response = await client.get(f'/api/artifacts/{uid}/distribution-readiness')
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['original_text'] == 'كلمة ' * 1000
        assert body['ai_required'] is False
        assert body['central_approval'] == 'APPROVED'
        assert all(target['approval'] == 'INHERITED' for target in body['targets'])
        assert all(target['execution_status'] == 'NOT_AUTHORIZED' for target in body['targets'])
        assert all(target['copy_status'] == 'BLOCKED' for target in body['targets'])
        async with SessionFactory() as session:
            after = [(await session.execute(select(func.count()).select_from(model))).scalar_one() for model in [PublicationModel, ScheduleModel]]
        assert before == after


@pytest.mark.asyncio
async def test_selection_batch_atomicity_clear_idempotence_and_source_conflict():
    ids = [await _seed_text_artifact('أصل قصير'), await _seed_text_artifact('أصل آخر')]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for uid in ids:
            await client.post(f'/api/artifacts/{uid}/approve', json={})
        rows = [(await client.get(f'/api/artifacts/{uid}/distribution-readiness')).json() for uid in ids]
        payload = {'artifact_ids': ids, 'platforms': ['telegram', 'youtube'], 'fingerprints': {row['artifact_id']: row['source_fingerprint'] for row in rows}}
        first = await client.post('/api/artifacts/distribution-selection', json=payload)
        assert first.status_code == 200, first.text
        assert first.json()['saved'] == 2
        assert first.json()['publications_created'] == first.json()['schedules_created'] == 0
        for _ in range(2):
            again = await client.post('/api/artifacts/distribution-selection', json=payload)
            assert again.status_code == 200, again.text
            assert all(not item['selection_stale'] for item in again.json()['items'])
        async with SessionFactory() as session:
            row = await session.get(ArtifactModel, UUID(ids[1]))
            row.content = 'تغيير متزامن'
            await session.commit()
        stale = await client.post('/api/artifacts/distribution-selection', json={**payload, 'platforms': []})
        assert stale.status_code == 409
        unchanged = (await client.get(f'/api/artifacts/{ids[0]}/distribution-readiness')).json()
        assert unchanged['selection']['platforms'] == ['telegram', 'youtube']
        changed = (await client.get(f'/api/artifacts/{ids[1]}/distribution-readiness')).json()
        assert changed['selection_stale'] is True
        payload['fingerprints'][ids[1]] = changed['source_fingerprint']
        clear = await client.post('/api/artifacts/distribution-selection', json={**payload, 'platforms': []})
        assert clear.status_code == 200
        assert all(not any(target['selected'] for target in row['targets']) for row in clear.json()['items'])
        for bad in [{**payload, 'platforms':['unknown']}, {**payload, 'artifact_ids':[ids[0],ids[0]]}]:
            assert (await client.post('/api/artifacts/distribution-selection',json=bad)).status_code == 409


@pytest.mark.asyncio
async def test_selection_cannot_approve_draft_or_grant_execution():
    uid = await _seed_text_artifact('غير معتمد')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        body = (await client.get(f'/api/artifacts/{uid}/distribution-readiness')).json()
        response = await client.post('/api/artifacts/distribution-selection',json={'artifact_ids':[uid], 'platforms':['telegram'], 'fingerprints':{uid:body['source_fingerprint']}})
        assert response.status_code == 409
        assert (await client.get(f'/api/artifacts/{uid}')).json()['review_status'] == 'DRAFT'
        assert (await client.post('/api/artifacts/distribution-selection',json={'artifact_ids':[uid], 'platforms':[], 'fingerprints':{}, 'execution_authorized':True})).status_code == 422


@pytest.mark.asyncio
async def test_distribution_selection_does_not_change_content_or_media_fingerprint():
    from app.application.telegram_albums import child_fingerprint
    uid = await _seed_text_artifact('محتوى ثابت')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        await client.post(f'/api/artifacts/{uid}/approve', json={})
        async with SessionFactory() as session:
            row = await session.get(ArtifactModel, UUID(uid))
            before = (row.content, dict(row.artifact_metadata), row.updated_at, row.reviewed_at, child_fingerprint(row))
        body = (await client.get(f'/api/artifacts/{uid}/distribution-readiness')).json()
        response = await client.post('/api/artifacts/distribution-selection', json={'artifact_ids':[uid], 'platforms':['telegram'], 'fingerprints':{uid:body['source_fingerprint']}})
        assert response.status_code == 200, response.text
        async with SessionFactory() as session:
            row = await session.get(ArtifactModel, UUID(uid))
            after = (row.content, dict(row.artifact_metadata), row.updated_at, row.reviewed_at, child_fingerprint(row))
        assert before == after
