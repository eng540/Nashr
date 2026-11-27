from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock
import httpx
import pytest
from app.application.analytics_capabilities import capabilities, report_binding, SPECS
from app.api.auth import issue_token, SESSION_COOKIE
from app.infrastructure.database.session import get_session
from app.main import app


def row(scopes=None, **extra):
    return dict(identity='saved-account', scopes=scopes, enabled=False,
                connected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                last_check_at=None, last_check_ok=False, token_expires_at=None, **extra)


@pytest.mark.parametrize('key,model,identity,required,evidence,url', SPECS)
def test_each_login_branch_preserves_unknown_and_does_not_diagnose_health(key, model, identity, required, evidence, url):
    r = report_binding(key, row(list(required)), required, evidence, url)
    assert r['current_provider_validation'] == 'NOT_ATTEMPTED'
    assert r['metrics_status'] == 'NOT_IMPLEMENTED'
    assert r['app_access_review'] == 'UNKNOWN'
    assert r['dependency_mapping'] == 'INCOMPLETE'
    assert 'baseline' not in json.dumps(r)
    assert r['audience_active_times'] == 'UNCONFIRMED_UNAVAILABLE'
    assert r['enabled_locally'] is False and r['last_check_ok'] is False
    assert r['requested_scopes'] is None and r['configured_scopes'] is None
    assert r['granted_scopes_at_saved_evidence'] == (sorted(required) if evidence else None)
    assert r['missing_from_saved_scope_evidence'] == ([] if required and evidence else None)
    if required and evidence:
        assert r['scope_status'] == 'CORE_PRESENT_DEPENDENCIES_UNMAPPED'


@pytest.mark.parametrize('scopes', [None, 'instagram_manage_insights', [1], {'scope': 'all'}])
def test_malformed_evidence_is_unknown(scopes):
    r = report_binding('ig', row(scopes), ('instagram_manage_insights',), 'stored_token_debug_scopes', None)
    assert r['granted_scopes_at_saved_evidence'] is None
    assert r['missing_from_saved_scope_evidence'] is None
    assert r['scope_status'] == 'GRANT_EVIDENCE_UNKNOWN'


def test_absent_and_known_missing_are_distinct():
    a = report_binding('ig', None, ('instagram_manage_insights',), 'stored_token_debug_scopes', None)
    b = report_binding('ig', row([]), ('instagram_manage_insights',), 'stored_token_debug_scopes', None)
    assert a['scope_status'] == 'NO_SAVED_CONNECTION'
    assert a['missing_from_saved_scope_evidence'] is None
    assert b['scope_status'] == 'MISSING_FROM_SAVED_EVIDENCE'
    assert b['missing_from_saved_scope_evidence'] == ['instagram_manage_insights']


class Result:
    def mappings(self): return self
    def one_or_none(self): return None


@pytest.mark.asyncio
async def test_only_safe_columns_no_writes_no_provider(monkeypatch):
    async def no_network(*args, **kwargs): raise AssertionError('Provider call forbidden')
    monkeypatch.setattr(httpx.AsyncClient, 'request', no_network)
    session = AsyncMock()
    session.execute.return_value = Result()
    r = await capabilities(session)
    assert len(r['bindings']) == 4 and r['provider_requests'] == 0
    assert r['metrics_fetched'] is False
    for call in session.execute.call_args_list:
        sql = str(call.args[0])
        assert sql.startswith('SELECT ')
        assert all(x not in sql for x in ('ciphertext', 'config_hash', 'tasks', 'app_settings'))
    session.commit.assert_not_called()
    session.flush.assert_not_called()
    assert not session.add.called


@pytest.mark.asyncio
async def test_owner_only_no_store_read_route(monkeypatch):
    monkeypatch.setenv('NASHR_AUTH_PASSWORD', 'test-owner')
    monkeypatch.setenv('NASHR_SESSION_SECRET', 'test-session-secret')
    session = AsyncMock()
    session.execute.return_value = Result()
    async def dependency(): yield session
    app.dependency_overrides[get_session] = dependency
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as c:
            denied = await c.get('/api/analytics/capabilities')
            assert denied.status_code == 401
            assert session.execute.await_count == 0
            c.cookies.set(SESSION_COOKIE, issue_token('admin'))
            response = await c.get('/api/analytics/capabilities')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-store'
            assert response.json()['mode'] == 'STORED_EVIDENCE_ONLY'
            assert len(response.json()['bindings']) == 4
    finally:
        app.dependency_overrides.pop(get_session, None)
