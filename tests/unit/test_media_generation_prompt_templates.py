import pytest

from app.domain.recipes import RecipeStage, validate_recipe_stage_configuration


def test_image_recipe_accepts_editable_generation_prompt_with_required_variables() -> None:
    stage = RecipeStage(
        key="image",
        capability_key="produce_image_artifact",
        capability_version=1,
        configuration={
            "generation_prompt": (
                "{{audience}} {{experience}} {{source_title}} {{source_name}} "
                "{{source_excerpt}} {{style_instructions}}"
            ),
            "aspect_ratio": "4:5",
            "image_size": "1K",
        },
    )
    validate_recipe_stage_configuration(stage)


def test_video_recipe_rejects_generation_prompt_missing_editorial_context() -> None:
    stage = RecipeStage(
        key="video",
        capability_key="produce_video_artifact",
        capability_version=1,
        configuration={
            "generation_prompt": (
                "{{audience}} {{experience}} {{source_title}} {{source_name}} "
                "{{source_excerpt}} {{style_instructions}}"
            ),
            "aspect_ratio": "9:16",
            "resolution": "720p",
            "duration_seconds": 5,
        },
    )
    with pytest.raises(ValueError, match="missing required variables"):
        validate_recipe_stage_configuration(stage)


def test_recipe_rejects_unknown_generation_prompt_variables() -> None:
    stage = RecipeStage(
        key="image",
        capability_key="produce_image_artifact",
        capability_version=1,
        configuration={
            "generation_prompt": (
                "{{audience}} {{experience}} {{source_title}} {{source_name}} "
                "{{source_excerpt}} {{style_instructions}} {{unknown}}"
            ),
        },
    )
    with pytest.raises(ValueError, match="unsupported variables"):
        validate_recipe_stage_configuration(stage)
