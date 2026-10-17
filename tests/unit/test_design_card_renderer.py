import pytest

from app.application.design_card_renderer import CardRenderConfig, render_arabic_text_card_png
from app.domain.recipes import RecipeStage, SUPPORTED_RECIPE_CAPABILITIES, validate_recipe_stage_configuration


def test_card_renderer_requires_approved_text():
    with pytest.raises(ValueError, match="non-empty approved"):
        render_arabic_text_card_png("  ")


def test_card_configuration_accepts_bounded_product_values():
    config = CardRenderConfig.from_mapping({
        "width": 1080,
        "height": 1350,
        "padding": 80,
        "background": "#FAF6EE",
        "foreground": "#202020",
        "font_size": 40,
        "line_spacing": 16,
        "max_lines": 24,
    })
    assert config.width == 1080
    assert config.background == "#FAF6EE"


def test_card_configuration_rejects_unknown_and_unsafe_values():
    with pytest.raises(ValueError, match="Unsupported"):
        CardRenderConfig.from_mapping({"arbitrary_html": "<script>"})
    with pytest.raises(ValueError, match="dimensions"):
        CardRenderConfig.from_mapping({"width": 10})


def test_card_recipe_capability_is_registered_and_configuration_is_validated():
    assert ("render_approved_text_card", 1) in SUPPORTED_RECIPE_CAPABILITIES
    validate_recipe_stage_configuration(RecipeStage(
        key="render-card",
        capability_key="render_approved_text_card",
        capability_version=1,
        configuration={"width": 1080, "height": 1350, "font_size": 40},
    ))
    with pytest.raises(ValueError, match="unsupported fields"):
        validate_recipe_stage_configuration(RecipeStage(
            key="render-card",
            capability_key="render_approved_text_card",
            capability_version=1,
            configuration={"generation_prompt": "rewrite text"},
        ))
