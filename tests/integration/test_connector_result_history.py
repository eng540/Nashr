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


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['TEXT','IMAGE'])
async def test_confirmed_facebook_runtime_copy_is_visible_in_material_history_and_queue(kind):
    from app.infrastructure.database.models import FacebookExecutionModel as Page
    token='page-history-'+uuid4().hex
    uid=await _seed_text_artifact(token); now=datetime.now(timezone.utc)
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid)); a.review_status='APPROVED'
        j=Page(artifact_id=a.id,page_id='123',source_fingerprint='a'*64,copy_version=1,kind=kind,message=token,total_bytes=0,runtime_snapshot={'connection':{'page_id':'123'},'message':token,'private':'PRIVATE_SNAPSHOT'},runtime_hash='b'*64,evidence_ref='owner-session:page_history_123',approved_until=now-timedelta(hours=1),state='PUBLISHED_AT_LAST_CHECK',post_id='123_456',permalink='https://www.facebook.com/123/posts/456',created_at=now,updated_at=now)
        s.add(j); await s.commit(); jid=j.id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        r=await c.get(f'/api/artifacts/{uid}/publications'); assert r.status_code==200,r.text
        rows=r.json()['connector_items']; assert len(rows)==1
        assert rows[0]['id']==str(jid) and rows[0]['confirmed'] is True
        assert rows[0]['platform']=='facebook'
        assert rows[0]['permalink']=='https://www.facebook.com/123/posts/456'
        assert 'PRIVATE_' not in str(rows) and 'page_history_123' not in str(rows)
        q=(await c.get('/api/publishing-queue',params={'q':token})).json()['items'][0]
        assert q['state']=='PUBLISHED'
        assert next(x for x in q['publication_outcomes'] if x['platform']=='facebook')['confirmed_targets']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['dormant','synthetic','draft','cancelled','wrong_page','unknown','known_id','invalid_id','bad_link','no_link','userinfo','port','fragment','null_id','other_post','other_page','vanity_unverified'])
async def test_facebook_history_preserves_provenance_and_confirmation_boundaries(condition):
    from app.infrastructure.database.models import FacebookExecutionModel as Page
    token='page-history-boundary-'+uuid4().hex
    uid=await _seed_text_artifact(token); now=datetime.now(timezone.utc)
    states={'draft':'DRAFT','cancelled':'CANCELLED','unknown':'OUTCOME_UNKNOWN','known_id':'POST_ID_KNOWN'}
    async with SessionFactory() as s:
        a=await s.get(ArtifactModel,UUID(uid)); a.review_status='APPROVED'
        j=Page(artifact_id=a.id,page_id='123',source_fingerprint='a'*64,copy_version=1,kind='TEXT',message=token,total_bytes=0,runtime_snapshot=None if condition=='dormant' else {'connection':{'page_id':'999' if condition=='wrong_page' else '123'},'secret':'PRIVATE_TOKEN'},runtime_hash='b'*64,evidence_ref='synthetic:test' if condition=='synthetic' else 'trusted-message:boundary_test_123',state=states.get(condition,'PUBLISHED_AT_LAST_CHECK'),post_id=None if condition=='null_id' else '999_456' if condition=='invalid_id' else '123_456',permalink={'bad_link':'https://evil.invalid/path','no_link':None,'userinfo':'https://facebook.com@evil.invalid/456','port':'https://www.facebook.com:8443/123/posts/456','fragment':'https://www.facebook.com/123/posts/456#fragment','other_post':'https://www.facebook.com/123/posts/999','other_page':'https://www.facebook.com/999/posts/456','vanity_unverified':'https://www.facebook.com/unverified-name/posts/456'}.get(condition,'https://www.facebook.com/123/posts/456'),created_at=now,updated_at=now)
        s.add(j); await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        rows=(await c.get(f'/api/artifacts/{uid}/publications')).json()['connector_items']
        q=(await c.get('/api/publishing-queue',params={'q':token})).json()['items'][0]
        if condition in {'dormant','synthetic','draft','cancelled','wrong_page'}:
            assert rows==[] and q['state']=='APPROVED'
        elif condition in {'unknown','known_id','invalid_id','null_id'}:
            assert len(rows)==1 and rows[0]['confirmed'] is False and rows[0]['permalink'] is None
            assert q['state']=='ATTENTION'
        else:
            assert rows[0]['confirmed'] is True and rows[0]['permalink'] is None
            assert q['state']=='PUBLISHED'
        assert 'PRIVATE_' not in str(rows) and 'boundary_test_123' not in str(rows)


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['https://www.facebook.com/123/posts/456','https://facebook.com/123/posts/456/','https://www.facebook.com/permalink.php?story_fbid=456&id=123','https://facebook.com/permalink.php?id=123&story_fbid=456'])
async def test_facebook_history_exposes_only_permalink_bound_to_exact_page_and_post(url):
    from app.infrastructure.database.models import FacebookExecutionModel as Page
    token='page-link-'+uuid4().hex
    uid=await _seed_text_artifact(token); now=datetime.now(timezone.utc)
    async with SessionFactory() as s:
        j=Page(artifact_id=UUID(uid),page_id='123',source_fingerprint='a'*64,copy_version=1,kind='TEXT',message=token,total_bytes=0,runtime_snapshot={'connection':{'page_id':'123'}},runtime_hash='b'*64,evidence_ref='owner-session:exact_link_123',state='PUBLISHED_AT_LAST_CHECK',post_id='123_456',permalink=url,created_at=now,updated_at=now)
        s.add(j); await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        row=(await c.get(f'/api/artifacts/{uid}/publications')).json()['connector_items'][0]
        assert row['confirmed'] is True and row['permalink']==url
