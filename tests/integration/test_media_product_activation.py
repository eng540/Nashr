from uuid import uuid4

import pytest

from app.application.product_control_plane import ProductionProductControlPlaneService
from app.application.recipe_control_plane import ProductionRecipeControlPlaneService
from app.domain.recipes import RecipeStage, validate_recipe_stage_configuration
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

@pytest.mark.asyncio
async def test_active_media_recipes_pin_editable_generation_prompt_templates():
    async with SessionFactory() as session:
        recipes = ProductionRecipeControlPlaneService(session)
        for key, capability in (
            ("BOOK_TO_IMAGE_ARTIFACT", "produce_image_artifact"),
            ("BOOK_TO_VIDEO_ARTIFACT", "produce_video_artifact"),
        ):
            recipe = await recipes.get_recipe(key)
            active = next(version for version in recipe["versions"] if version["status"] == "PUBLISHED")
            stage = next(stage for stage in active["stages"] if stage["capability_key"] == capability)
            assert active["version"] >= 2
            assert isinstance(stage["configuration"].get("generation_prompt"), str)
            assert stage["configuration"]["generation_prompt"].strip()
            validate_recipe_stage_configuration(RecipeStage.from_dict(stage))

@pytest.mark.asyncio
async def test_new_media_recipe_cannot_publish_without_editable_generation_prompt():
    recipe_key = f"TEST_IMAGE_PROMPT_RECIPE_{uuid4().hex.upper()}"
    base_stage = {
        "key": "generate-image",
        "capability_key": "produce_image_artifact",
        "capability_version": 1,
        "configuration": {"aspect_ratio": "1:1", "image_size": "1K"},
    }
    valid_stage = {
        **base_stage,
        "configuration": {
            **base_stage["configuration"],
            "generation_prompt": (
                "{{audience}} {{experience}} {{source_title}} {{source_name}} "
                "{{source_excerpt}} {{identity_context}} {{style_instructions}}"
            ),
        },
    }
    async with SessionFactory() as session:
        recipes = ProductionRecipeControlPlaneService(session)
        await recipes.create_recipe(
            recipe_key,
            "Editable image prompt test",
            "Ensure new media recipes do not rely on code-fixed prompts.",
            [base_stage],
        )
        with pytest.raises(ValueError, match="generation_prompt"):
            await recipes.publish(recipe_key, 1)
        await recipes.update_draft(recipe_key, 1, [valid_stage])
        published = await recipes.publish(recipe_key, 1)
        assert published["status"] == "PUBLISHED"
