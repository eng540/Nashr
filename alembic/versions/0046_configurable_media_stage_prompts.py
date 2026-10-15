"""Move built-in image/video generation directives into versioned recipe configuration."""
from __future__ import annotations

import json
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "0046_configurable_media_stage_prompts"
down_revision: Union[str, Sequence[str], None] = "0045_versioned_discovery_prompts"
branch_labels = None
depends_on = None


IMAGE_PROMPT_TEMPLATE = """Create one original, high-quality editorial illustration inspired by the source material below.
Do not include readable text, captions, logos, or watermarks unless the recipe instructions explicitly require them.
Respect the source's cultural context; do not invent named people or historical facts.

Audience: {{audience}}
Intended experience: {{experience}}
Source title: {{source_title}}
Source name: {{source_name}}
Source material (bounded excerpt):
{{source_excerpt}}

Visual direction:
{{style_instructions}}"""

VIDEO_PROMPT_TEMPLATE = """Create a short, coherent, source-grounded editorial video inspired by the material below.
Avoid captions, logos, or watermarks; do not invent historical facts or named people.
Use culturally respectful visual storytelling.

Audience: {{audience}}
Intended experience: {{experience}}
Source title: {{source_title}}
Source name: {{source_name}}
Source material (bounded excerpt):
{{source_excerpt}}

Pinned editorial instructions and identity context (must be followed):
{{editorial_prompt}}

Visual direction:
{{style_instructions}}"""


RECIPE_TEMPLATES = {
    "BOOK_TO_IMAGE_ARTIFACT": ("produce_image_artifact", IMAGE_PROMPT_TEMPLATE),
    "BOOK_TO_VIDEO_ARTIFACT": ("produce_video_artifact", VIDEO_PROMPT_TEMPLATE),
}


def _new_recipe_version(bind, recipe_key: str, capability_key: str, prompt_template: str):
    active = bind.execute(sa.text("""
        SELECT r.id AS recipe_id, rv.id AS version_id, rv.version, rv.definition
        FROM production_recipes r
        JOIN production_recipe_versions rv ON rv.recipe_id = r.id
        WHERE r.key = :key AND rv.status = 'PUBLISHED'
    """), {"key": recipe_key}).mappings().one_or_none()
    if active is None:
        raise RuntimeError(f"Cannot configure media prompt: published recipe '{recipe_key}' is missing.")

    definition = json.loads(json.dumps(active["definition"]))
    stages = definition.get("stages")
    if not isinstance(stages, list) or not stages:
        raise RuntimeError(f"Cannot configure media prompt: recipe '{recipe_key}' has no stages.")
    matching = [stage for stage in stages if stage.get("capability_key") == capability_key]
    if len(matching) != 1:
        raise RuntimeError(f"Cannot configure media prompt: recipe '{recipe_key}' must contain exactly one {capability_key} stage.")
    configuration = matching[0].setdefault("configuration", {})
    if configuration.get("generation_prompt"):
        return None

    configuration["generation_prompt"] = prompt_template
    latest = bind.execute(sa.text("""
        SELECT COALESCE(MAX(version), 0) FROM production_recipe_versions WHERE recipe_id = :recipe_id
    """), {"recipe_id": active["recipe_id"]}).scalar_one()
    new_version_id = uuid4()
    new_version = int(latest) + 1

    bind.execute(sa.text("""
        UPDATE production_recipe_versions SET status = 'ARCHIVED'
        WHERE id = :id AND status = 'PUBLISHED'
    """), {"id": active["version_id"]})
    bind.execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (:id, :recipe_id, :version, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "id": new_version_id,
        "recipe_id": active["recipe_id"],
        "version": new_version,
        "definition": json.dumps(definition, ensure_ascii=False),
    })
    bind.execute(sa.text("""
        INSERT INTO media_prompt_recipe_versions (recipe_version_id, previous_version_id)
        VALUES (:new_id, :previous_id)
    """), {"new_id": str(new_version_id), "previous_id": str(active["version_id"])})
    return {
        "recipe_key": recipe_key,
        "recipe_id": active["recipe_id"],
        "old_version_id": str(active["version_id"]),
        "new_version_id": str(new_version_id),
        "new_version": new_version,
    }


def _upgrade_active_product_versions(bind, recipe_info):
    if recipe_info is None:
        return
    products = bind.execute(sa.text("""
        SELECT pv.id AS product_version_id, pv.product_id, pv.version, pv.definition
        FROM production_product_versions pv
        WHERE pv.status = 'PUBLISHED'
          AND pv.definition->'component_versions'->'recipe'->>'key' = :recipe_key
          AND pv.definition->'component_versions'->'recipe'->>'version_id' = :old_recipe_version_id
        ORDER BY pv.product_id, pv.version
    """), {
        "recipe_key": recipe_info["recipe_key"],
        "old_recipe_version_id": recipe_info["old_version_id"],
    }).mappings().all()

    for product in products:
        definition = json.loads(json.dumps(product["definition"]))
        component_versions = definition.get("component_versions")
        recipe_reference = component_versions.get("recipe") if isinstance(component_versions, dict) else None
        if not isinstance(recipe_reference, dict):
            continue
        recipe_reference["version_id"] = recipe_info["new_version_id"]
        recipe_reference["version"] = recipe_info["new_version"]

        latest = bind.execute(sa.text("""
            SELECT COALESCE(MAX(version), 0) FROM production_product_versions WHERE product_id = :product_id
        """), {"product_id": product["product_id"]}).scalar_one()
        new_product_version_id = uuid4()
        bind.execute(sa.text("""
            UPDATE production_product_versions SET status = 'ARCHIVED'
            WHERE id = :id AND status = 'PUBLISHED'
        """), {"id": product["product_version_id"]})
        bind.execute(sa.text("""
            INSERT INTO production_product_versions (id, product_id, version, definition, status)
            VALUES (:id, :product_id, :version, CAST(:definition AS JSONB), 'PUBLISHED')
        """), {
            "id": new_product_version_id,
            "product_id": product["product_id"],
            "version": int(latest) + 1,
            "definition": json.dumps(definition, ensure_ascii=False),
        })
        bind.execute(sa.text("""
            INSERT INTO media_prompt_product_versions (product_version_id, previous_version_id)
            VALUES (:new_id, :previous_id)
        """), {"new_id": str(new_product_version_id), "previous_id": str(product["product_version_id"])})

    drafts = bind.execute(sa.text("""
        SELECT pv.id AS product_version_id, pv.definition
        FROM production_product_versions pv
        WHERE pv.status = 'DRAFT'
          AND pv.definition->'component_versions'->'recipe'->>'key' = :recipe_key
          AND pv.definition->'component_versions'->'recipe'->>'version_id' = :old_recipe_version_id
    """), {
        "recipe_key": recipe_info["recipe_key"],
        "old_recipe_version_id": recipe_info["old_version_id"],
    }).mappings().all()
    for draft in drafts:
        previous_definition = json.loads(json.dumps(draft["definition"]))
        definition = json.loads(json.dumps(previous_definition))
        recipe_reference = definition["component_versions"]["recipe"]
        recipe_reference["version_id"] = recipe_info["new_version_id"]
        recipe_reference["version"] = recipe_info["new_version"]
        bind.execute(sa.text("""
            UPDATE production_product_versions SET definition = CAST(:definition AS JSONB)
            WHERE id = :id AND status = 'DRAFT'
        """), {
            "id": draft["product_version_id"],
            "definition": json.dumps(definition, ensure_ascii=False),
        })
        bind.execute(sa.text("""
            INSERT INTO media_prompt_updated_drafts
                (product_version_id, new_recipe_version_id, previous_definition)
            VALUES (:product_version_id, :new_recipe_version_id, CAST(:previous_definition AS JSONB))
        """), {
            "product_version_id": str(draft["product_version_id"]),
            "new_recipe_version_id": recipe_info["new_version_id"],
            "previous_definition": json.dumps(previous_definition, ensure_ascii=False),
        })


def upgrade() -> None:
    op.create_table(
        "media_prompt_recipe_versions",
        sa.Column("recipe_version_id", sa.String(length=36), primary_key=True),
        sa.Column("previous_version_id", sa.String(length=36), nullable=False),
    )
    op.create_table(
        "media_prompt_product_versions",
        sa.Column("product_version_id", sa.String(length=36), primary_key=True),
        sa.Column("previous_version_id", sa.String(length=36), nullable=False),
    )
    op.create_table(
        "media_prompt_updated_drafts",
        sa.Column("product_version_id", sa.String(length=36), primary_key=True),
        sa.Column("new_recipe_version_id", sa.String(length=36), nullable=False),
        sa.Column("previous_definition", sa.JSON(), nullable=False),
    )
    bind = op.get_bind()
    for recipe_key, (capability_key, prompt_template) in RECIPE_TEMPLATES.items():
        recipe_info = _new_recipe_version(bind, recipe_key, capability_key, prompt_template)
        _upgrade_active_product_versions(bind, recipe_info)


def downgrade() -> None:
    bind = op.get_bind()
    recipe_versions = bind.execute(sa.text("""
        SELECT recipe_version_id, previous_version_id FROM media_prompt_recipe_versions
    """)).mappings().all()
    product_versions = bind.execute(sa.text("""
        SELECT product_version_id, previous_version_id FROM media_prompt_product_versions
    """)).mappings().all()
    updated_drafts = bind.execute(sa.text("""
        SELECT product_version_id, new_recipe_version_id, previous_definition
        FROM media_prompt_updated_drafts
    """)).mappings().all()
    for row in updated_drafts:
        current = bind.execute(sa.text("""
            SELECT status, definition FROM production_product_versions WHERE id = :id
        """), {"id": row["product_version_id"]}).mappings().one_or_none()
        if current is None or current["status"] != "DRAFT":
            raise RuntimeError("Cannot downgrade media prompt migration: an updated draft is no longer a draft.")
        current_recipe_id = current["definition"].get("component_versions", {}).get("recipe", {}).get("version_id")
        if current_recipe_id != row["new_recipe_version_id"]:
            raise RuntimeError("Cannot downgrade media prompt migration: an updated draft was edited after migration.")

    for row in product_versions:
        referenced = bind.execute(sa.text("""
            SELECT 1 FROM production_jobs
            WHERE resolved_context->'product'->>'version_id' = :version_id
            UNION ALL
            SELECT 1 FROM production_products WHERE derived_from_version_id = CAST(:version_id AS UUID)
            LIMIT 1
        """), {"version_id": row["product_version_id"]}).scalar_one_or_none()
        if referenced is not None:
            raise RuntimeError("Cannot downgrade media prompt migration: a generated product version is in use.")

    for row in product_versions:
        bind.execute(sa.text("DELETE FROM production_product_versions WHERE id = :id"), {"id": row["product_version_id"]})
        bind.execute(sa.text("UPDATE production_product_versions SET status = 'PUBLISHED' WHERE id = :id"), {"id": row["previous_version_id"]})
    for row in updated_drafts:
        bind.execute(sa.text("""
            UPDATE production_product_versions SET definition = CAST(:definition AS JSONB)
            WHERE id = :id AND status = 'DRAFT'
        """), {
            "id": row["product_version_id"],
            "definition": json.dumps(row["previous_definition"], ensure_ascii=False),
        })

    for row in recipe_versions:
        referenced = bind.execute(sa.text("""
            SELECT 1 FROM production_jobs
            WHERE resolved_context->'recipe'->>'version_id' = :version_id
            UNION ALL
            SELECT 1 FROM production_product_versions
            WHERE definition->'component_versions'->'recipe'->>'version_id' = :version_id
            LIMIT 1
        """), {"version_id": row["recipe_version_id"]}).scalar_one_or_none()
        if referenced is not None:
            raise RuntimeError("Cannot downgrade media prompt migration: a generated recipe version is in use.")

    for row in recipe_versions:
        bind.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = :id"), {"id": row["recipe_version_id"]})
        bind.execute(sa.text("UPDATE production_recipe_versions SET status = 'PUBLISHED' WHERE id = :id"), {"id": row["previous_version_id"]})

    op.drop_table("media_prompt_updated_drafts")
    op.drop_table("media_prompt_product_versions")
    op.drop_table("media_prompt_recipe_versions")
