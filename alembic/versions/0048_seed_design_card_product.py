"""Seed a published, deterministic approved-text card product."""
from typing import Sequence, Union
import json
from uuid import UUID

from alembic import op
import sqlalchemy as sa

revision: str = "0048_seed_design_card_product"
down_revision: Union[str, Sequence[str], None] = "0047_seed_thematic_text_product"
branch_labels = None
depends_on = None

RECIPE_ID = UUID("00000000-0000-0000-0000-000000001301")
RECIPE_VERSION_ID = UUID("00000000-0000-0000-0000-000000001302")
PRODUCT_ID = UUID("00000000-0000-0000-0000-000000001303")
PRODUCT_VERSION_ID = UUID("00000000-0000-0000-0000-000000001304")
RECIPE_KEY = "APPROVED_TEXT_TO_DESIGN_CARD"
PRODUCT_KEY = "ARABIC_LITERATURE_DESIGN_CARD"


def upgrade() -> None:
    bind = op.get_bind()
    reserved = bind.execute(sa.text("""
        SELECT 1 FROM production_recipes WHERE id = :recipe_id OR key = :recipe_key
        UNION ALL SELECT 1 FROM production_recipe_versions WHERE id = :recipe_version_id
        UNION ALL SELECT 1 FROM production_products WHERE id = :product_id OR key = :product_key
        UNION ALL SELECT 1 FROM production_product_versions WHERE id = :product_version_id
        LIMIT 1
    """), {
        "recipe_id": RECIPE_ID,
        "recipe_key": RECIPE_KEY,
        "recipe_version_id": RECIPE_VERSION_ID,
        "product_id": PRODUCT_ID,
        "product_key": PRODUCT_KEY,
        "product_version_id": PRODUCT_VERSION_ID,
    }).scalar_one_or_none()
    if reserved is not None:
        raise RuntimeError("Cannot seed the design-card product because a reserved identifier or key already exists; inspect it rather than overwriting it.")

    prompt = bind.execute(sa.text("""
        SELECT pt.key, ptv.id AS version_id, ptv.version
        FROM prompt_templates pt
        JOIN prompt_template_versions ptv ON ptv.prompt_template_id = pt.id
        WHERE pt.key = 'editorial.drafter' AND ptv.status = 'PUBLISHED'
        ORDER BY ptv.version DESC LIMIT 1
    """)).mappings().one_or_none()
    identity = bind.execute(sa.text("""
        SELECT i.key, iv.id AS version_id, iv.version
        FROM editorial_identities i
        JOIN editorial_identity_versions iv ON iv.identity_id = i.id
        WHERE i.key = 'ARABIC_LITERATURE_BASELINE_V1' AND iv.status = 'PUBLISHED'
        ORDER BY iv.version DESC LIMIT 1
    """)).mappings().one_or_none()
    policy = bind.execute(sa.text("""
        SELECT p.key, pv.id AS version_id, pv.version
        FROM production_policies p
        JOIN production_policy_versions pv ON pv.policy_id = p.id
        WHERE p.key = 'EDITORIAL_DEFAULT' AND pv.status = 'PUBLISHED'
        ORDER BY pv.version DESC LIMIT 1
    """)).mappings().one_or_none()
    contract = bind.execute(sa.text("""
        SELECT c.key, cv.id AS version_id, cv.version
        FROM output_contracts c
        JOIN output_contract_versions cv ON cv.contract_id = c.id
        WHERE c.key = 'IMAGE_ARTIFACT' AND cv.status = 'PUBLISHED'
        ORDER BY cv.version DESC LIMIT 1
    """)).mappings().one_or_none()
    missing = [name for name, value in (
        ("published editorial prompt", prompt),
        ("published baseline identity", identity),
        ("published editorial policy", policy),
        ("published IMAGE_ARTIFACT output contract", contract),
    ) if value is None]
    if missing:
        raise RuntimeError("Cannot seed design-card product; missing " + ", ".join(missing) + ".")

    recipe_definition = {
        "stages": [{
            "key": "render-approved-card",
            "capability_key": "render_approved_text_card",
            "capability_version": 1,
            "configuration": {
                "width": 1080,
                "height": 1350,
                "padding": 88,
                "background": "#F7F2E8",
                "foreground": "#24211D",
                "font_size": 42,
                "line_spacing": 18,
                "max_lines": 22,
                "font_family": "naskh",
                "show_title": True,
                "show_source_attribution": True,
                "title_font_size": 34,
                "attribution_font_size": 22,
                "text_alignment": "right",
            },
        }]
    }
    bind.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": RECIPE_ID,
        "key": RECIPE_KEY,
        "name": "Approved text to deterministic design card",
        "purpose": "Render a human-approved TEXT Artifact into an independently reviewable Arabic PNG card.",
    })
    bind.execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (:version_id, :recipe_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "version_id": RECIPE_VERSION_ID,
        "recipe_id": RECIPE_ID,
        "definition": json.dumps(recipe_definition, ensure_ascii=False),
    })

    product_definition = {
        "recipe_key": RECIPE_KEY,
        "output_contract_key": contract["key"],
        "policy_key": policy["key"],
        "audience": "Readers of Arabic literature and culture",
        "experience": "An Arabic text card with the approved text preserved exactly, ready for independent visual review",
        "prompt_key": prompt["key"],
        "identity_key": identity["key"],
        "component_versions": {
            "prompt": {"key": prompt["key"], "version_id": str(prompt["version_id"]), "version": prompt["version"]},
            "identity": {"key": identity["key"], "version_id": str(identity["version_id"]), "version": identity["version"]},
            "recipe": {"key": RECIPE_KEY, "version_id": str(RECIPE_VERSION_ID), "version": 1},
            "policy": {"key": policy["key"], "version_id": str(policy["version_id"]), "version": policy["version"]},
            "output_contract": {"key": contract["key"], "version_id": str(contract["version_id"]), "version": contract["version"]},
        },
    }
    bind.execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": PRODUCT_ID,
        "key": PRODUCT_KEY,
        "name": "Arabic Literature Design Card",
        "purpose": "Create a deterministic visual derivative from an already-approved text Artifact.",
    })
    bind.execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (:version_id, :product_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "version_id": PRODUCT_VERSION_ID,
        "product_id": PRODUCT_ID,
        "definition": json.dumps(product_definition, ensure_ascii=False),
    })


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, identifier in (
        ("production_product_versions", "id", PRODUCT_VERSION_ID),
        ("production_products", "id", PRODUCT_ID),
        ("production_recipe_versions", "id", RECIPE_VERSION_ID),
        ("production_recipes", "id", RECIPE_ID),
    ):
        bind.execute(sa.text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": identifier})
