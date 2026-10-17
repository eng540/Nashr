"""Seed distinct, version-pinned deterministic and AI-assisted design-card products."""
from typing import Sequence, Union
import json
from uuid import UUID

from alembic import op
import sqlalchemy as sa

revision: str = "0049_seed_design_card_variants"
down_revision: Union[str, Sequence[str], None] = "0048_seed_design_card_product"
branch_labels = None
depends_on = None

BASE_PRODUCT_VERSION_ID = UUID("00000000-0000-0000-0000-000000001304")

VARIANTS = (
    {
        "recipe_id": UUID("00000000-0000-0000-0000-000000001311"),
        "recipe_version_id": UUID("00000000-0000-0000-0000-000000001312"),
        "product_id": UUID("00000000-0000-0000-0000-000000001313"),
        "product_version_id": UUID("00000000-0000-0000-0000-000000001314"),
        "recipe_key": "APPROVED_ARABIC_QUOTE_CARD",
        "product_key": "ARABIC_QUOTE_CARD",
        "product_name": "Arabic Quote Card",
        "purpose": "A centered quote card with no automatic title or attribution.",
        "configuration": {
            "width": 1080, "height": 1350, "padding": 96,
            "background": "#F7F2E8", "foreground": "#24211D",
            "font_size": 48, "line_spacing": 22, "max_lines": 18,
            "font_family": "naskh", "show_title": False,
            "show_source_attribution": False, "title_font_size": 34,
            "attribution_font_size": 22, "text_alignment": "center",
        },
    },
    {
        "recipe_id": UUID("00000000-0000-0000-0000-000000001321"),
        "recipe_version_id": UUID("00000000-0000-0000-0000-000000001322"),
        "product_id": UUID("00000000-0000-0000-0000-000000001323"),
        "product_version_id": UUID("00000000-0000-0000-0000-000000001324"),
        "recipe_key": "APPROVED_TEXT_SOURCE_CARD",
        "product_key": "ARABIC_TEXT_SOURCE_CARD",
        "product_name": "Arabic Text and Source Card",
        "purpose": "A right-aligned Arabic text card with title and source attribution.",
        "configuration": {
            "width": 1080, "height": 1350, "padding": 88,
            "background": "#F7F2E8", "foreground": "#24211D",
            "font_size": 42, "line_spacing": 18, "max_lines": 22,
            "font_family": "naskh", "show_title": True,
            "show_source_attribution": True, "title_font_size": 34,
            "attribution_font_size": 22, "text_alignment": "right",
        },
    },
    {
        "recipe_id": UUID("00000000-0000-0000-0000-000000001331"),
        "recipe_version_id": UUID("00000000-0000-0000-0000-000000001332"),
        "product_id": UUID("00000000-0000-0000-0000-000000001333"),
        "product_version_id": UUID("00000000-0000-0000-0000-000000001334"),
        "recipe_key": "APPROVED_ARABIC_POETRY_CARD",
        "product_key": "ARABIC_POETRY_CARD",
        "product_name": "Arabic Poetry Card",
        "purpose": "A centered literary or poetry layout that retains source line ordering.",
        "configuration": {
            "width": 1080, "height": 1350, "padding": 88,
            "background": "#F7F2E8", "foreground": "#24211D",
            "font_size": 44, "line_spacing": 26, "max_lines": 24,
            "font_family": "naskh", "show_title": False,
            "show_source_attribution": True, "title_font_size": 34,
            "attribution_font_size": 22, "text_alignment": "center",
        },
    },
    {
        "recipe_id": UUID("00000000-0000-0000-0000-000000001341"),
        "recipe_version_id": UUID("00000000-0000-0000-0000-000000001342"),
        "product_id": UUID("00000000-0000-0000-0000-000000001343"),
        "product_version_id": UUID("00000000-0000-0000-0000-000000001344"),
        "recipe_key": "APPROVED_ARTISTIC_BACKGROUND_CARD",
        "product_key": "ARABIC_ARTISTIC_CARD",
        "product_name": "Arabic Artistic Background Card",
        "purpose": "An optional AI-generated, text-free artistic background with deterministic Arabic typesetting.",
        "configuration": {
            "width": 1080, "height": 1350, "padding": 88,
            "background": "#F7F2E8", "foreground": "#24211D",
            "font_size": 42, "line_spacing": 18, "max_lines": 22,
            "font_family": "naskh", "show_title": True,
            "show_source_attribution": True, "title_font_size": 34,
            "attribution_font_size": 22, "text_alignment": "right",
            "background_mode": "ai_generated",
            "background_prompt": "أنشئ خلفية فنية أدبية راقية مستوحاة من المخطوطات العربية والورق الطبيعي، بتكوين هادئ ومساحات سالبة واسعة وتباين منخفض خلف منطقة النص. الخلفية وحدها دون أي حروف أو كلمات أو أرقام أو شعارات أو علامات مائية.",
            "background_overlay_color": "#F7F2E8",
            "background_overlay_opacity": 225,
            "provider": "fal", "model": "fal-ai/flux/schnell",
            "aspect_ratio": "4:5", "image_size": "1K",
        },
    },
)


def upgrade() -> None:
    bind = op.get_bind()
    base = bind.execute(sa.text("""
        SELECT definition FROM production_product_versions
        WHERE id = :id AND status = 'PUBLISHED'
    """), {"id": BASE_PRODUCT_VERSION_ID}).scalar_one_or_none()
    if base is None:
        raise RuntimeError("Cannot seed design variants without the published base design-card product.")
    base_definition = dict(base)

    for variant in VARIANTS:
        reserved = bind.execute(sa.text("""
            SELECT 1 FROM production_recipes WHERE id = :recipe_id OR key = :recipe_key
            UNION ALL SELECT 1 FROM production_recipe_versions WHERE id = :recipe_version_id
            UNION ALL SELECT 1 FROM production_products WHERE id = :product_id OR key = :product_key
            UNION ALL SELECT 1 FROM production_product_versions WHERE id = :product_version_id
            LIMIT 1
        """), {
            "recipe_id": variant["recipe_id"],
            "recipe_key": variant["recipe_key"],
            "recipe_version_id": variant["recipe_version_id"],
            "product_id": variant["product_id"],
            "product_key": variant["product_key"],
            "product_version_id": variant["product_version_id"],
        }).scalar_one_or_none()
        if reserved is not None:
            raise RuntimeError(f"Cannot seed design variant {variant['product_key']}; inspect the reserved identifier or key.")

        recipe_definition = {
            "stages": [{
                "key": "render-approved-card",
                "capability_key": "render_approved_text_card",
                "capability_version": 1,
                "configuration": variant["configuration"],
            }]
        }
        bind.execute(sa.text("""
            INSERT INTO production_recipes (id, key, name, purpose)
            VALUES (:id, :key, :name, :purpose)
        """), {
            "id": variant["recipe_id"],
            "key": variant["recipe_key"],
            "name": variant["product_name"],
            "purpose": variant["purpose"],
        })
        bind.execute(sa.text("""
            INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
            VALUES (:version_id, :recipe_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
        """), {
            "version_id": variant["recipe_version_id"],
            "recipe_id": variant["recipe_id"],
            "definition": json.dumps(recipe_definition, ensure_ascii=False),
        })

        product_definition = dict(base_definition)
        product_definition["recipe_key"] = variant["recipe_key"]
        component_versions = dict(product_definition["component_versions"])
        component_versions["recipe"] = {
            "key": variant["recipe_key"],
            "version_id": str(variant["recipe_version_id"]),
            "version": 1,
        }
        product_definition["component_versions"] = component_versions
        bind.execute(sa.text("""
            INSERT INTO production_products (id, key, name, purpose)
            VALUES (:id, :key, :name, :purpose)
        """), {
            "id": variant["product_id"],
            "key": variant["product_key"],
            "name": variant["product_name"],
            "purpose": variant["purpose"],
        })
        bind.execute(sa.text("""
            INSERT INTO production_product_versions (id, product_id, version, definition, status)
            VALUES (:version_id, :product_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
        """), {
            "version_id": variant["product_version_id"],
            "product_id": variant["product_id"],
            "definition": json.dumps(product_definition, ensure_ascii=False),
        })


def downgrade() -> None:
    bind = op.get_bind()
    for variant in reversed(VARIANTS):
        for table, identifier in (
            ("production_product_versions", variant["product_version_id"]),
            ("production_products", variant["product_id"]),
            ("production_recipe_versions", variant["recipe_version_id"]),
            ("production_recipes", variant["recipe_id"]),
        ):
            bind.execute(sa.text(f"DELETE FROM {table} WHERE id = :id"), {"id": identifier})
