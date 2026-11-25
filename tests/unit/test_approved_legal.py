import httpx
import pytest
from app.main import app
from app.api.legal import PAGES

@pytest.mark.asyncio
async def test_public_legal_routes_keep_private_workspace_gated(monkeypatch):
    monkeypatch.setenv('NASHR_AUTH_PASSWORD','test-only-gate')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
        for path in ['/terms','/privacy']:
            response=await client.get(path)
            assert response.status_code==200
            assert 'eng.alfakih@gmail.com' in response.text
            assert 'عبدالمجيد الفقيه' in response.text
            assert '<html lang="ar" dir="rtl">' in response.text
            assert 'بعد الموافقة' not in response.text
        assert (await client.get('/api/connections')).status_code==401
        assert (await client.get('/bank')).status_code==401
        assert (await client.get('/terms/extra')).status_code==401
        assert (await client.post('/terms')).status_code==405
