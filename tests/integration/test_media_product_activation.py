import pytest

from app.application.product_control_plane import ProductionProductControlPlaneService
from app.infrastructure.database.session import SessionFactory


@pytest.mark.asyncio
async def test_image_product_stays_inactive_until_durable_storage_is_configured(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "ARTIFACT_STORAGE_ENDPOINT_URL",
        "ARTIFACT_STORAGE_BUCKET",
        "ARTIFACT_STORAGE_ACCESS_KEY_ID",
        "ARTIFACT_STORAGE_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    async with SessionFactory() as session:
        service = ProductionProductControlPlaneService(session)
        products = await service.list_products()
        image_product = next(item for item in products if item["key"] == "ARABIC_LITERATURE_IMAGE")
        assert image_product["active_version"] is None
        with pytest.raises(ValueError, match="durable ARTIFACT_STORAGE"):
            await service.publish("ARABIC_LITERATURE_IMAGE", 1)
        video_product = next(item for item in products if item["key"] == "ARABIC_LITERATURE_VIDEO")
        assert video_product["active_version"] is None
        with pytest.raises(ValueError, match="durable ARTIFACT_STORAGE"):
            await service.publish("ARABIC_LITERATURE_VIDEO", 1)
