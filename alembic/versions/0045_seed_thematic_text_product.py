"""Seed a version-pinned product for multi-source thematic text composition."""
from typing import Sequence, Union
from uuid import UUID
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0045_seed_thematic_text_product"
down_revision: Union[str, Sequence[str], None] = "0044_product_derivation_lineage"
branch_labels = None
depends_on = None

RECIPE_ID = "00000000-0000-0000-0000-000000001201"
RECIPE_VERSION_ID = "00000000-0000-0000-0000-000000001202"
PRODUCT_ID = "00000000-0000-0000-0000-000000001203"
PRODUCT_VERSION_ID = "00000000-0000-0000-0000-000000001204"
RECIPE_KEY = "BOOK_TO_THEMATIC_TEXT_ARTIFACT"
PRODUCT_KEY = "ARABIC_LITERATURE_THEMATIC_TEXT"


def upgrade() -> None:
    bind = op.get_bind()
    reserved = bind.execute(sa.text("""
        SELECT 1 FROM production_recipes WHERE id = :recipe_id OR key = :recipe_key
        UNION ALL SELECT 1 FROM production_recipe_versions WHERE id = :recipe_version_id
        UNION ALL SELECT 1 FROM production_products WHERE id = :product_id OR key = :product_key
        UNION ALL SELECT 1 FROM production_product_versions WHERE id = :product_version_id
        LIMIT 1
    """), {
        "recipe_id": UUID(RECIPE_ID),
        "recipe_key": RECIPE_KEY,
        "recipe_version_id": UUID(RECIPE_VERSION_ID),
        "product_id": UUID(PRODUCT_ID),
        "product_key": PRODUCT_KEY,
        "product_version_id": UUID(PRODUCT_VERSION_ID),
    }).scalar_one_or_none()
    if reserved is not None:
        raise RuntimeError(
            "Cannot seed the thematic text product because a reserved identifier or key already exists; inspect it rather than overwriting it."
        )

    prompt = bind.execute(sa.text("""
        SELECT pt.key, ptv.id AS version_id, ptv.version
        FROM prompt_templates pt
        JOIN prompt_template_versions ptv ON ptv.prompt_template_id = pt.id
        WHERE pt.key = 'editorial.drafter' AND ptv.status = 'PUBLISHED'
        ORDER BY ptv.version DESC
        LIMIT 1
    """)).mappings().one_or_none()
    identity = bind.execute(sa.text("""
        SELECT i.key, iv.id AS version_id, iv.version
        FROM editorial_identities i
        JOIN editorial_identity_versions iv ON iv.identity_id = i.id
        WHERE i.key = 'ARABIC_LITERATURE_BASELINE_V1' AND iv.status = 'PUBLISHED'
        ORDER BY iv.version DESC
        LIMIT 1
    """)).mappings().one_or_none()
    policy = bind.execute(sa.text("""
        SELECT p.key, pv.id AS version_id, pv.version
        FROM production_policies p
        JOIN production_policy_versions pv ON pv.policy_id = p.id
        WHERE p.key = 'EDITORIAL_DEFAULT' AND pv.status = 'PUBLISHED'
        ORDER BY pv.version DESC
        LIMIT 1
    """)).mappings().one_or_none()
    contract = bind.execute(sa.text("""
        SELECT c.key, cv.id AS version_id, cv.version
        FROM output_contracts c
        JOIN output_contract_versions cv ON cv.contract_id = c.id
        WHERE c.key = 'TEXT_ARTIFACT' AND cv.status = 'PUBLISHED'
        ORDER BY cv.version DESC
        LIMIT 1
    """)).mappings().one_or_none()
    missing = [
        name for name, value in (
            ("published editorial prompt", prompt),
            ("published baseline identity", identity),
            ("published editorial policy", policy),
            ("published TEXT_ARTIFACT output contract", contract),
        ) if value is None
    ]
    if missing:
        raise RuntimeError("Cannot seed thematic text product; missing " + ", ".join(missing) + ".")

    recipe_definition = {
        "stages": [{
            "key": "compose-thematic-text",
            "capability_key": "compose_thematic_artifact",
            "capability_version": 1,
        }]
    }
    bind.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": UUID(RECIPE_ID),
        "key": RECIPE_KEY,
        "name": "Multi-source thematic text",
        "purpose": "Compose one reviewable text Artifact from an explicit selection of materials across books.",
    })
    bind.execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (:version_id, :recipe_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "version_id": UUID(RECIPE_VERSION_ID),
        "recipe_id": UUID(RECIPE_ID),
        "definition": json.dumps(recipe_definition, ensure_ascii=False),
    })

    product_definition = {
        "recipe_key": RECIPE_KEY,
        "output_contract_key": contract["key"],
        "policy_key": policy["key"],
        "audience": "Readers of Arabic literature and culture",
        "experience": "A source-grounded thematic text artifact with traceable sources, ready for human review",
        "prompt_key": prompt["key"],
        "identity_key": identity["key"],
        "component_versions": {
            "prompt": {"key": prompt["key"], "version_id": str(prompt["version_id"]), "version": prompt["version"]},
            "identity": {"key": identity["key"], "version_id": str(identity["version_id"]), "version": identity["version"]},
            "recipe": {"key": RECIPE_KEY, "version_id": RECIPE_VERSION_ID, "version": 1},
            "policy": {"key": policy["key"], "version_id": str(policy["version_id"]), "version": policy["version"]},
            "output_contract": {"key": contract["key"], "version_id": str(contract["version_id"]), "version": contract["version"]},
        },
    }
    bind.execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": UUID(PRODUCT_ID),
        "key": PRODUCT_KEY,
        "name": "Arabic Literature Thematic Text",
        "purpose": "Produce a thematic text from selected materials across multiple books while preserving source provenance.",
    })
    bind.execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (:version_id, :product_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "version_id": UUID(PRODUCT_VERSION_ID),
        "product_id": UUID(PRODUCT_ID),
        "definition": json.dumps(product_definition, ensure_ascii=False),
    })


def downgrade() -> None:
    bind = op.get_bind()
    for table, expression, identifier in (
        ("production_jobs", "resolved_context->'product'->>'version_id'", PRODUCT_VERSION_ID),
        ("production_jobs", "resolved_context->'recipe'->>'version_id'", RECIPE_VERSION_ID),
        ("artifacts", "resolved_context->'product'->>'version_id'", PRODUCT_VERSION_ID),
        ("artifacts", "resolved_context->'recipe'->>'version_id'", RECIPE_VERSION_ID),
    ):
        referenced = bind.execute(sa.text(f"SELECT 1 FROM {table} WHERE {expression} = :id LIMIT 1"), {"id": identifier}).scalar_one_or_none()
        if referenced is not None:
            raise RuntimeError(
                "Cannot downgrade thematic text product seed: a production job or Artifact references the product or recipe version."
            )
    bind.execute(sa.text("DELETE FROM production_product_versions WHERE id = :id"), {"id": UUID(PRODUCT_VERSION_ID)})
    bind.execute(sa.text("DELETE FROM production_products WHERE id = :id"), {"id": UUID(PRODUCT_ID)})
    bind.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = :id"), {"id": UUID(RECIPE_VERSION_ID)})
    bind.execute(sa.text("DELETE FROM production_recipes WHERE id = :id"), {"id": UUID(RECIPE_ID)})
