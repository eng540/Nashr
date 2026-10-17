from pathlib import Path

import pytest
from PIL import Image

from app.application.design_card_renderer import CardRenderConfig, render_arabic_text_card_png, resolve_card_font_path
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
    assert CardRenderConfig.from_mapping({"font_family": "naskh"}).font_family == "naskh"


def test_card_configuration_rejects_unknown_and_unsafe_values():
    with pytest.raises(ValueError, match="Unsupported"):
        CardRenderConfig.from_mapping({"arbitrary_html": "<script>"})
    with pytest.raises(ValueError, match="dimensions"):
        CardRenderConfig.from_mapping({"width": 10})
    with pytest.raises(ValueError, match="font_family"):
        CardRenderConfig.from_mapping({"font_family": []})


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



def test_arabic_card_renders_png_and_fails_instead_of_truncating():
    font_path = resolve_card_font_path("naskh")

    png = render_arabic_text_card_png(
        "إِنَّ اللغةَ العربيةَ جميلةٌ.\n\nوهذه فقرةٌ ثانيةٌ.",
        {"width": 640, "height": 800, "padding": 40, "font_size": 30, "line_spacing": 10, "max_lines": 20, "show_source_attribution": True},
        title="عنوان تجريبي",
        attribution="المصدر: كتاب تجريبي",
        font_path=font_path,
    )
    assert png.startswith(bytes.fromhex("89504e470d0a1a0a"))
    assert png == render_arabic_text_card_png(
        "إِنَّ اللغةَ العربيةَ جميلةٌ.\n\nوهذه فقرةٌ ثانيةٌ.",
        {"width": 640, "height": 800, "padding": 40, "font_size": 30, "line_spacing": 10, "max_lines": 20, "show_source_attribution": True},
        title="عنوان تجريبي",
        attribution="المصدر: كتاب تجريبي",
        font_path=font_path,
    )
    with Image.open(__import__("io").BytesIO(png)) as image:
        assert image.format == "PNG"
        assert image.size == (640, 800)

    with pytest.raises(ValueError, match="allows"):
        render_arabic_text_card_png(
            ("هذه جملة طويلة لا بد أن تتجاوز عدد الأسطر المسموح به عند حجم الخط المحدد. " * 8).strip(),
            {"width": 640, "height": 800, "padding": 40, "font_size": 30, "line_spacing": 10, "max_lines": 1},
            font_path=font_path,
        )


def test_packaged_naskh_font_is_available_and_licensed():
    font_path = Path(resolve_card_font_path("naskh"))
    assert font_path.is_file()
    assert font_path.name == "NotoNaskhArabic[wght].ttf"
    assert (font_path.parent / "OFL.txt").is_file()
