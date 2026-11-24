import httpx,pytest
from app.main import app
from tests.integration.test_managed_connections import browser,config

@pytest.mark.asyncio
async def test_requirements_owner_only_read_no_writes(config,monkeypatch):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
        assert (await client.get('/api/connections/tiktok/requirements')).status_code==401
    async with browser() as client:
        r=await client.get('/api/connections/tiktok/requirements');assert r.status_code==200
        d=r.json();assert r.headers['cache-control']=='no-store'
        assert not any(d[x] for x in ['execution_enabled','account_connected','upload_enabled','approval_recorded'])
        assert {x['scope'] for x in d['modes']}=={'video.upload','video.publish'}
        assert all(x['url'].startswith('https://developers.tiktok.com/') for x in d['sources'])
        assert (await client.post('/api/connections/tiktok/requirements',json={})).status_code==405
