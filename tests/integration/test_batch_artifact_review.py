from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select, func
from app.main import app
from app.application.manual_artifacts import create_manual_artifact
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel, PlatformCopyModel, PublicationModel, ScheduleModel

async def drafts(count=2):
    async with SessionFactory() as session:
        return [(await create_manual_artifact(session,kind='TEXT',title=f'مادة {n}',content=f'نص محفوظ كامل {n}')).id for n in range(count)]

@pytest.mark.asyncio
async def test_preview_is_readonly_and_approval_is_atomic_with_exact_copies():
    ids=await drafts()
    async with SessionFactory() as session:
        before={uid:(await session.get(ArtifactModel,uid)).content for uid in ids}
        counts=[(await session.execute(select(func.count()).select_from(model))).scalar_one() for model in [PublicationModel,ScheduleModel]]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        preview=await client.post('/api/artifacts/batch-review/preview',json={'artifact_ids':list(map(str,ids))})
        assert preview.status_code==200,preview.text
        items=preview.json()['items']
        assert [i['id'] for i in items]==list(map(str,ids))
        assert all(i['review_status']=='DRAFT' for i in items)
        async with SessionFactory() as session:
            for uid in ids:
                assert (await session.get(ArtifactModel,uid)).review_status=='DRAFT'
            assert not (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id.in_(ids)))).scalars().all()
        result=await client.post('/api/artifacts/batch-review/approve',json={'artifact_ids':list(map(str,ids)),'fingerprints':{i['id']:i['review_fingerprint'] for i in items}})
        assert result.status_code==200,result.text
        assert result.json()['publishing_authorized'] is False
        assert (await client.post('/api/artifacts/batch-review/approve',json={'artifact_ids':list(map(str,ids)),'fingerprints':{i['id']:i['review_fingerprint'] for i in items}})).status_code==409
    async with SessionFactory() as session:
        for uid in ids:
            row=await session.get(ArtifactModel,uid)
            assert row.review_status=='APPROVED' and row.content==before[uid]
            copies=(await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==uid))).scalars().all()
            assert len(copies)==6
            assert all(c.fields['description']==before[uid] for c in copies)
        assert counts==[(await session.execute(select(func.count()).select_from(model))).scalar_one() for model in [PublicationModel,ScheduleModel]]

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['text','state','missing','provenance','variant','fingerprint'])
async def test_invalid_or_changed_member_never_partially_approves(change):
    ids=await drafts()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        preview=(await client.post('/api/artifacts/batch-review/preview',json={'artifact_ids':list(map(str,ids))})).json()
        fingerprints={i['id']:i['review_fingerprint'] for i in preview['items']}
        async with SessionFactory() as session:
            row=await session.get(ArtifactModel,ids[1])
            if change=='text':row.content='تغيير محفوظ بعد المعاينة'
            elif change=='state':row.review_status='REJECTED'
            elif change=='provenance':row.resolved_context={}
            elif change=='variant':row.artifact_metadata={**row.artifact_metadata,'source_type':'PLATFORM_VARIANT'}
            await session.commit()
        requested=list(map(str,ids))
        if change=='missing':requested[1]=str(uuid4())
        if change=='fingerprint':fingerprints[str(ids[1])]='incorrect'
        result=await client.post('/api/artifacts/batch-review/approve',json={'artifact_ids':requested,'fingerprints':fingerprints})
        assert result.status_code in [404,409],result.text
    async with SessionFactory() as session:
        assert (await session.get(ArtifactModel,ids[0])).review_status=='DRAFT'
        assert not (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id.in_(ids)))).scalars().all()

@pytest.mark.asyncio
async def test_batch_rejects_empty_duplicate_and_oversized_requests():
    ids=await drafts(1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for values,status in [([],422),([str(ids[0])]*2,409),([str(uuid4()) for _ in range(101)],422)]:
            response=await client.post('/api/artifacts/batch-review/preview',json={'artifact_ids':values})
            assert response.status_code==status,response.text

@pytest.mark.asyncio
async def test_copy_preparation_failure_rolls_back_every_approval(monkeypatch):
    from app.application.central_platform_copies import prepare_copies
    ids=await drafts()
    calls=0
    async def failing(session,row):
        nonlocal calls
        calls+=1
        if calls==2:raise ValueError('Synthetic preparation failure')
        return await prepare_copies(session,row)
    monkeypatch.setattr('app.application.central_platform_copies.prepare_copies',failing)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        items=(await client.post('/api/artifacts/batch-review/preview',json={'artifact_ids':list(map(str,ids))})).json()['items']
        result=await client.post('/api/artifacts/batch-review/approve',json={'artifact_ids':list(map(str,ids)),'fingerprints':{i['id']:i['review_fingerprint'] for i in items}})
        assert result.status_code==409,result.text
    async with SessionFactory() as session:
        for uid in ids:assert (await session.get(ArtifactModel,uid)).review_status=='DRAFT'
        assert not (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id.in_(ids)))).scalars().all()
