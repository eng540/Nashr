from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import FacebookExecutionModel as Page
from tests.integration.test_instagram_oauth import config, browser
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['TEXT', 'IMAGE'])
@pytest.mark.parametrize('link,expected', [
    ('https://www.facebook.com/123/posts/999', None),
    ('https://www.facebook.com/999/posts/456', None),
    ('https://www.facebook.com/unverified/posts/456', None),
    ('https://facebook.com@evil.invalid/123/posts/456', None),
    ('https://www.facebook.com:8443/123/posts/456', None),
    ('https://www.facebook.com/123/posts/456#fragment', None),
    ('https://www.facebook.com/permalink.php?story_fbid=999&id=123', None),
    ('https://evil.invalid/123/posts/456', None),
    (None, None),
    ('https://www.facebook.com/123/posts/456', 'same'),
    ('https://facebook.com/123/posts/456/', 'same'),
    ('https://www.facebook.com/permalink.php?story_fbid=456&id=123', 'same'),
    ('https://facebook.com/permalink.php?id=123&story_fbid=456', 'same'),
])
async def test_operation_list_binds_page_result_link_to_saved_post(config, kind, link, expected):
    uid = await _seed_text_artifact('operation-link-' + uuid4().hex)
    now = datetime.now(timezone.utc)
    async with SessionFactory() as s:
        job = Page(artifact_id=UUID(uid), page_id='123', source_fingerprint='a'*64,
            copy_version=1, kind=kind, message='saved original', total_bytes=0,
            runtime_snapshot={'connection': {'page_id': '123', 'page_name': 'Page'}},
            evidence_ref='owner-session:operation_test_123', state='PUBLISHED_AT_LAST_CHECK',
            post_id='123_456', permalink=link,
            created_at=now, updated_at=now)
        s.add(job)
        await s.commit()
        jid = str(job.id)
    async with browser() as c:
        response = await c.get('/api/platform-operations?limit=100')
        assert response.status_code == 200
        row = next(r for r in response.json()['items'] if r['id'] == jid)
        assert row['permalink'] == (link if expected == 'same' else None)
        assert row['state'] == 'PUBLISHED_AT_LAST_CHECK'
        assert row['execution_state'] == 'PUBLISHED_AT_LAST_CHECK'
        assert not any(x in response.text for x in ['runtime_snapshot', 'evidence_ref', 'source_fingerprint'])


@pytest.mark.asyncio
@pytest.mark.parametrize('state,post_id', [
    ('PUBLISHED_AT_LAST_CHECK', None),
    ('PUBLISHED_AT_LAST_CHECK', '999_456'),
    ('PUBLISHED_AT_LAST_CHECK', '123_abc'),
    ('POST_ID_KNOWN', '123_456'),
    ('OUTCOME_UNKNOWN', '123_456'),
])
async def test_operation_link_needs_numeric_bound_id_and_confirmed_state(config, state, post_id):
    uid = await _seed_text_artifact('operation-boundary-' + uuid4().hex)
    async with SessionFactory() as s:
        job = Page(artifact_id=UUID(uid), page_id='123', source_fingerprint='a'*64,
            copy_version=1, kind='IMAGE', message='saved original', total_bytes=0,
            runtime_snapshot={'connection': {'page_id': '123', 'page_name': 'Page'}},
            evidence_ref='owner-session:operation_test_456', state=state,
            post_id=post_id, permalink='https://www.facebook.com/123/posts/456')
        s.add(job)
        await s.commit()
        jid = str(job.id)
    async with browser() as c:
        response = await c.get('/api/platform-operations?limit=100&platform=facebook_photo')
        assert response.status_code == 200
        row = next(r for r in response.json()['items'] if r['id'] == jid)
        assert row['permalink'] is None
        assert row['state'] == state
