import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_image_product_cannot_be_published_without_durable_storage(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "OBJECT_STORAGE_ENDPOINT_URL",
        "OBJECT_STORAGE_BUCKET",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_REGION",
    ):
        monkeypatch.delenv(name, raising=False)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        detail = await client.get("/api/control/products/ARABIC_LITERATURE_IMAGE")
        assert detail.status_code == 200, detail.text
        assert detail.json()["active_version"] is None
        publish = await client.post("/api/control/products/ARABIC_LITERATURE_IMAGE/versions/1/publish")
        assert publish.status_code == 409
        assert "Durable object storage" in publish.json()["detail"]
        after = await client.get("/api/control/products/ARABIC_LITERATURE_IMAGE")
        assert after.status_code == 200
        assert after.json()["active_version"] is None
