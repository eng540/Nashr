from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
import httpx
import pytest
from sqlalchemy import select, func
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel, InstagramExecutionModel as IG, InstagramPublishDecisionModel as Decision, FacebookReelJobModel as FB, PublicationModel
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
async def test_connector_history_requires_provenance_and_external_result_and_never_leaks_snapshots():
    token='connector-history-'+uuid4().hex
    uid=await _seed_text_artifact(token)
    now=datetime.now(timezone.utc)
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid));a.review_status='APPROVED'
        def ig(state='PUBLISHED',link='https://www.instagram.com/reel/Confirmed_1/',mode='UNIFIED'):
            return IG(artifact_id=a.id,account_id='123',connection_binding={'login_mode':mode,'token_hash':'PRIVATE_HASH'},source_fingerprint='a'*64,copy_version=1,media_sha256='b'*64,kind='VIDEO',caption=token,alt_text='',state=state,media_id='456',permalink=link,created_at=now,updated_at=now)
        good,synthetic,bad_link,unbound=ig(),ig(),ig(link='https://evil.invalid/'),ig(mode='DIRECT')
        s.add_all([good,synthetic,bad_link,unbound]);await s.flush()
        for j in [good,bad_link,unbound]:s.add(Decision(execution_id=j.id,snapshot_hash='c'*64,snapshot={'secret':'PRIVATE_SNAPSHOT'},evidence_ref='trusted-message:test_evidence_123',state='APPROVED',created_at=now,expires_at=now+timedelta(hours=1)))
        s.add(FB(artifact_id=a.id,snapshot={'caption':token,'connection':{'page_id':'789','token_hash':'PRIVATE_HASH'}},snapshot_hash='d'*64,state='PUBLISHED',evidence_ref='owner-session:test_evidence_456',remote_session={'video_id':'987','upload_url':'PRIVATE_UPLOAD'},permalink='https://www.facebook.com/reel/987/',created_at=now,updated_at=now))
        await s.commit();before=(await s.execute(select(func.count()).select_from(PublicationModel))).scalar_one()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        r=await c.get(f'/api/artifacts/{uid}/publications');assert r.status_code==200,r.text
        data=r.json();assert data['total']==0;assert len(data['connector_items'])==3
        assert sum(x['confirmed'] for x in data['connector_items'])==2
        assert all('PRIVATE_' not in str(x) for x in data['connector_items'])
        assert all(x['permalink'] is None for x in data['connector_items'] if not x['confirmed'])
        q=await c.get('/api/publishing-queue',params={'q':token});assert q.status_code==200,q.text
        row=q.json()['items'][0];assert row['state']=='ATTENTION'
        assert {x['platform']:x['confirmed_targets'] for x in row['publication_outcomes']}=={'instagram':1,'facebook':1}
    async with SessionFactory() as s:
        job=await s.get(IG,bad_link.id);job.state='RETIRED_UNPUBLISHED';await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        row=(await c.get('/api/publishing-queue',params={'q':token})).json()['items'][0]
        assert row['state']=='PUBLISHED'
    async with SessionFactory() as s:assert (await s.execute(select(func.count()).select_from(PublicationModel))).scalar_one()==before
