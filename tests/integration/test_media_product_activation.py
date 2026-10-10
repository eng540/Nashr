from uuid import uuid4

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
        audio_product = next(item for item in products if item["key"] == "ARABIC_LITERATURE_AUDIO")
        assert audio_product["active_version"] is None
        with pytest.raises(ValueError, match="durable ARTIFACT_STORAGE"):
            await service.publish("ARABIC_LITERATURE_AUDIO", 1)


@pytest.mark.asyncio
async def test_product_publication_rejects_recipe_output_contract_mismatch():
    async with SessionFactory() as session:
        service = ProductionProductControlPlaneService(session)
        product_key = f"TEST_INCOMPATIBLE_IMAGE_PRODUCT_{uuid4().hex.upper()}"
        await service.create_product(
            product_key,
            "Incompatible image test",
            "Must not publish a mismatched output contract",
            {
                "recipe_key": "BOOK_TO_IMAGE_ARTIFACT",
                "output_contract_key": "TEXT_ARTIFACT",
                "policy_key": "EDITORIAL_DEFAULT",
                "audience": "Test audience",
                "experience": "Test experience",
            },
        )
        with pytest.raises(ValueError, match="incompatible with output contract"):
            await service.publish(product_key, 1)
