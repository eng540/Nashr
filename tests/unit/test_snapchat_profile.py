from uuid import uuid4
import httpx
import pytest
from app.adapters.publishing import snapchat_profile as edge

ID = '76da494b-76bc-4bbb-bb27-c5a66fb0d1ab'


def payload():
    return {'request_status': 'SUCCESS', 'public_profile': {
        'id': ID, 'display_name': 'Synthetic only', 'snap_user_name': 'synthetic',
        'phone_number': 'not-returned', 'email': 'not-returned',
        'logo_urls': {'original_logo_url': 'https://untrusted.invalid/private'}}}


def test_minimal_identity_only():
    result = edge.profile_identity(payload(), ID)
    assert result == {'profile_id': ID, 'display_name': 'Synthetic only', 'username': 'synthetic'}


@pytest.mark.parametrize('data', [None, [], {}, {'request_status': 'PARTIAL', 'public_profile': {}},
    {'request_status': 'ERROR', 'debug_message': 'private-provider-content'},
    {'request_status': 'SUCCESS', 'public_profiles': []}])
def test_fail_closed_responses(data):
    with pytest.raises(edge.SnapchatIdentityError, match='^PROFILE_IDENTITY$'):
        edge.profile_identity(data)


@pytest.mark.parametrize('field,value', [('id', 'invalid'), ('id', None), ('display_name', ''),
    ('display_name', 1), ('snap_user_name', []), ('snap_user_name', ' ' * 10)])
def test_invalid_identity_fields(field, value):
    data = payload(); data['public_profile'][field] = value
    with pytest.raises(edge.SnapchatIdentityError):
        edge.profile_identity(data)


def test_changed_profile_not_selected_silently():
    with pytest.raises(edge.SnapchatIdentityError):
        edge.profile_identity(payload(), str(uuid4()))


@pytest.mark.asyncio
async def test_official_get_only_no_redirect_and_minimal_fields():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=payload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (await edge.identity(client, 'synthetic-not-real-token', ID))['profile_id'] == ID
    assert len(calls) == 1 and calls[0].method == 'GET'
    assert str(calls[0].url) == edge.IDENTITY_URL
    assert calls[0].headers['authorization'] == 'Bearer synthetic-not-real-token'
    assert not calls[0].content


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [302, 401, 403, 429, 500])
async def test_provider_failure_and_redirect_never_followed(status):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={'location': 'https://untrusted.invalid'},
                              json={'debug_message': 'synthetic-private-token'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(edge.SnapchatIdentityError, match='^IDENTITY_CHECK$') as error:
            await edge.identity(client, 'synthetic-not-real-token', ID)
    assert 'private' not in str(error.value) and len(calls) == 1


@pytest.mark.asyncio
async def test_network_failure_not_leaked():
    def respond(request):
        raise httpx.ConnectError('synthetic-private-token', request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(edge.SnapchatIdentityError, match='^IDENTITY_CHECK$'):
            await edge.identity(client, 'synthetic-not-real-token')


@pytest.mark.asyncio
async def test_overview_exposes_unimplemented_requirements_without_provider(monkeypatch):
    from app.application import managed_connections
    class Rows:
        def scalars(self): return self
        def all(self): return []
    class Session:
        async def execute(self, query): return Rows()
        async def get(self, model, key): return None
    monkeypatch.delenv('NASHR_CONNECTION_ENCRYPTION_KEY', raising=False)
    result = await managed_connections.overview(Session())
    snap = next(row for row in result['platforms'] if row['key'] == 'snapchat')
    assert snap['state'] == 'NOT_IMPLEMENTED'
    assert 'snapchat-profile-api' in snap['requirements']
    assert 'قائمة السماح' in snap['requirements']
    assert result['execution_authorized'] is False
