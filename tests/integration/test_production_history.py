from uuid import uuid4
from datetime import datetime, timezone, timedelta
import httpx
import pytest
from sqlalchemy import select
from app.main import app
from app.infrastructure.database.models import ProductionJobModel, SourceModel
from app.infrastructure.database.session import SessionFactory

@pytest.mark.asyncio
async def test_history_is_paginated_filtered_read_only_and_routes_before_uuid():
    source_id=uuid4()
    now=datetime(2099,1,1,tzinfo=timezone.utc)
    ids=[uuid4(),uuid4(),uuid4()]
    async with SessionFactory() as session:
        session.add(SourceModel(id=source_id,filename='history-source.pdf',mime_type='application/pdf',storage_path='history',size_bytes=1,status='STORED'))
        await session.flush()
        for i,job_id in enumerate(ids):
            session.add(ProductionJobModel(id=job_id,source_id=source_id,scope='SOURCE',status='FAILED' if i==1 else 'COMPLETED',created_at=now+timedelta(seconds=i),total_items=2,completed_items=1,failed_items=1))
        await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        first=await client.get('/production-jobs?limit=1&offset=0')
        assert first.status_code==200
        assert first.json()['items'][0]['job_id']==str(ids[2])
        assert first.json()['items'][0]['filename']=='history-source.pdf'
        assert 'resolved_context' not in first.json()['items'][0]
        second=(await client.get('/production-jobs?limit=1&offset=1')).json()
        assert second['items'][0]['job_id']==str(ids[1])
        assert second['total']==first.json()['total']
        filtered=(await client.get('/production-jobs?state=FAILED&limit=100')).json()
        assert str(ids[1]) in [x['job_id'] for x in filtered['items']]
        assert all(x['status']=='FAILED' for x in filtered['items'])
        for query in ['limit=101','offset=-1','state=BOGUS']:
            assert (await client.get('/production-jobs?'+query)).status_code==422
    async with SessionFactory() as session:
        jobs=(await session.execute(select(ProductionJobModel).where(ProductionJobModel.id.in_(ids)))).scalars().all()
        assert len(jobs)==3
        assert {j.status for j in jobs}=={'COMPLETED','FAILED'}
        assert all(j.attempts==0 for j in jobs)
