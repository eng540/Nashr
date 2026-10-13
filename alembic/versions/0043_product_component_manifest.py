"""Bootstrap immutable component manifests for active built-in products.

Legacy product versions remain archived for historical provenance. This migration
creates new published versions instead of rewriting existing published records.
"""
from typing import Sequence, Union
import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "0043_product_component_manifest"
down_revision: Union[str, Sequence[str], None] = "0042_separate_production_claim"
branch_labels = None
depends_on = None

IDENTITY_ID = "00000000-0000-0000-0000-000000001101"
IDENTITY_VERSION_ID = "00000000-0000-0000-0000-000000001102"
IDENTITY_KEY = "ARABIC_LITERATURE_EDITORIAL"
PROMPT_KEY = "editorial.drafter"


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "product_manifest_bootstrap_versions",
        sa.Column("product_version_id", sa.String(length=36), primary_key=True),
        sa.Column("previous_version_id", sa.String(length=36), nullable=False),
    )
    op.create_table(
        "product_manifest_bootstrap_drafts",
        sa.Column("version_id", sa.String(length=36), primary_key=True),
        sa.Column("previous_definition", sa.JSON(), nullable=False),
    )
    identity_definition = {
        "purpose": "تحرير أدبي أمين للمصدر، يوازن بين إبراز القيمة الأصلية والتدخل بالقدر الضروري فقط.",
        "audience": "قراء الأدب العربي والثقافة واللغة.",
        "voice": "محرر أدبي وثقافي دقيق وأمين للمصدر.",
        "tone": "رصين، واضح، مقتصد، غير متكلف.",
        "principles": [
            "المادة الأصلية هي المرجع المركزي.",
            "لا تختلق معلومة أو دلالة لا يسندها المصدر.",
            "لا تجعل الشرح أو العبرة هدفًا تلقائيًا.",
            "قلل التدخل عندما يكون الأصل أقوى.",
        ],
        "objectives": [
            "إظهار القيمة الأدبية أو المعرفية الموجودة في المادة.",
            "إنتاج مخرج صالح للمراجعة البشرية.",
        ],
        "constraints": [
            "حافظ على معنى المصدر وهويته.",
            "لا تستبدل قواعد المنتج أو عقد المخرج.",
        ],
    }
    bind.execute(sa.text("""
        INSERT INTO editorial_identities (id, key, name, purpose)
        VALUES (:id, :key, :name, :purpose)
    """), {
        "id": IDENTITY_ID,
        "key": IDENTITY_KEY,
        "name": "الهوية الأدبية الأمينة للمصدر",
        "purpose": identity_definition["purpose"],
    })
    bind.execute(sa.text("""
        INSERT INTO editorial_identity_versions (id, identity_id, version, definition, status)
        VALUES (:version_id, :identity_id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "version_id": IDENTITY_VERSION_ID,
        "identity_id": IDENTITY_ID,
        "definition": json.dumps(identity_definition, ensure_ascii=False),
    })

    prompt = bind.execute(sa.text("""
        SELECT pt.id, pt.key, ptv.id AS version_id, ptv.version
        FROM prompt_templates pt
        JOIN prompt_template_versions ptv ON ptv.prompt_template_id = pt.id
        WHERE pt.key = :key AND ptv.status = 'PUBLISHED'
    """), {"key": PROMPT_KEY}).mappings().one_or_none()
    if prompt is None:
        raise RuntimeError("Cannot bootstrap product manifests: no published editorial.drafter prompt exists.")

    products = bind.execute(sa.text("""
        SELECT p.id AS product_id, p.key, pv.id AS product_version_id,
               pv.version AS product_version, pv.definition
        FROM production_products p
        JOIN production_product_versions pv ON pv.product_id = p.id
        WHERE pv.status = 'PUBLISHED'
          AND pv.definition->>'recipe_key' IS NOT NULL
          AND pv.definition->>'component_versions' IS NULL
          AND p.key IN (
              'ARABIC_LITERATURE_TELEGRAM_POST',
              'ARABIC_LITERATURE_BRIEF_TELEGRAM_POST',
              'ARABIC_LITERATURE_TEXT'
          )
        ORDER BY p.key
    """)).mappings().all()

    for product in products:
        definition = dict(product["definition"])
        recipe = bind.execute(sa.text("""
            SELECT r.id, r.key, rv.id AS version_id, rv.version
            FROM production_recipes r
            JOIN production_recipe_versions rv ON rv.recipe_id = r.id
            WHERE r.key = :key AND rv.status = 'PUBLISHED'
        """), {"key": definition["recipe_key"]}).mappings().one_or_none()
        policy = bind.execute(sa.text("""
            SELECT p.id, p.key, pv.id AS version_id, pv.version
            FROM production_policies p
            JOIN production_policy_versions pv ON pv.policy_id = p.id
            WHERE p.key = :key AND pv.status = 'PUBLISHED'
        """), {"key": definition["policy_key"]}).mappings().one_or_none()
        contract = bind.execute(sa.text("""
            SELECT c.id, c.key, cv.id AS version_id, cv.version
            FROM output_contracts c
            JOIN output_contract_versions cv ON cv.contract_id = c.id
            WHERE c.key = :key AND cv.status = 'PUBLISHED'
        """), {"key": definition["output_contract_key"]}).mappings().one_or_none()
        if recipe is None or policy is None or contract is None:
            raise RuntimeError(
                f"Cannot bootstrap product '{product['key']}': a published recipe, policy, or output contract is missing."
            )

        definition["prompt_key"] = PROMPT_KEY
        definition["identity_key"] = IDENTITY_KEY
        definition["component_versions"] = {
            "prompt": {"key": prompt["key"], "version_id": str(prompt["version_id"]), "version": prompt["version"]},
            "identity": {"key": IDENTITY_KEY, "version_id": IDENTITY_VERSION_ID, "version": 1},
            "recipe": {"key": recipe["key"], "version_id": str(recipe["version_id"]), "version": recipe["version"]},
            "policy": {"key": policy["key"], "version_id": str(policy["version_id"]), "version": policy["version"]},
            "output_contract": {"key": contract["key"], "version_id": str(contract["version_id"]), "version": contract["version"]},
        }
        latest = bind.execute(sa.text("""
            SELECT COALESCE(MAX(version), 0) AS version
            FROM production_product_versions WHERE product_id = :product_id
        """), {"product_id": product["product_id"]}).scalar_one()
        bind.execute(sa.text("""
            UPDATE production_product_versions SET status = 'ARCHIVED'
            WHERE id = :id AND status = 'PUBLISHED'
        """), {"id": product["product_version_id"]})
        created_version_id = str(uuid4())
        bind.execute(sa.text("""
            INSERT INTO production_product_versions (id, product_id, version, definition, status)
            VALUES (:id, :product_id, :version, CAST(:definition AS JSONB), 'PUBLISHED')
        """), {
            "id": created_version_id,
            "product_id": product["product_id"],
            "version": int(latest) + 1,
            "definition": json.dumps(definition, ensure_ascii=False),
        })
        bind.execute(sa.text("""
            INSERT INTO product_manifest_bootstrap_versions (product_version_id, previous_version_id)
            VALUES (:created_id, :previous_id)
        """), {"created_id": created_version_id, "previous_id": str(product["product_version_id"])})

    # Keep inactive built-in media drafts easy to complete in Control Plane; they
    # remain drafts and still require compatibility/storage checks before publish.
    drafts = bind.execute(sa.text("""
        SELECT pv.id, pv.definition
        FROM production_product_versions pv
        JOIN production_products p ON p.id = pv.product_id
        WHERE pv.status = 'DRAFT'
          AND pv.definition->>'recipe_key' IS NOT NULL
          AND pv.definition->>'prompt_key' IS NULL
          AND p.key IN ('ARABIC_LITERATURE_IMAGE', 'ARABIC_LITERATURE_VIDEO', 'ARABIC_LITERATURE_AUDIO')
    """)).mappings().all()
    for draft in drafts:
        bind.execute(sa.text("""
            INSERT INTO product_manifest_bootstrap_drafts (version_id, previous_definition)
            VALUES (:id, CAST(:definition AS JSONB))
        """), {"id": str(draft["id"]), "definition": json.dumps(draft["definition"], ensure_ascii=False)})
        bind.execute(sa.text("""
            UPDATE production_product_versions
            SET definition = definition || CAST(:references AS JSONB)
            WHERE id = :id
        """), {
            "id": str(draft["id"]),
            "references": json.dumps({"prompt_key": PROMPT_KEY, "identity_key": IDENTITY_KEY}),
        })


def downgrade() -> None:
    bind = op.get_bind()
    created = bind.execute(sa.text("""
        SELECT product_version_id, previous_version_id
        FROM product_manifest_bootstrap_versions
    """)).mappings().all()
    for row in created:
        referenced = bind.execute(sa.text("""
            SELECT 1 FROM production_jobs
            WHERE resolved_context->'product'->>'version_id' = :version_id
            LIMIT 1
        """), {"version_id": row["product_version_id"]}).scalar_one_or_none()
        if referenced is not None:
            raise RuntimeError(
                "Cannot downgrade product manifest bootstrap: a production job references a bootstrapped product version."
            )
    external_reference = bind.execute(sa.text("""
        SELECT 1 FROM production_product_versions
        WHERE definition->'component_versions'->'identity'->>'version_id' = :identity_version
          AND id NOT IN (SELECT product_version_id FROM product_manifest_bootstrap_versions)
        LIMIT 1
    """), {"identity_version": IDENTITY_VERSION_ID}).scalar_one_or_none()
    if external_reference is not None:
        raise RuntimeError(
            "Cannot downgrade product manifest bootstrap: another product version references the bootstrap identity."
        )

    changed_drafts = bind.execute(sa.text("""
        SELECT d.version_id, d.previous_definition, pv.definition, pv.status
        FROM product_manifest_bootstrap_drafts d
        JOIN production_product_versions pv ON pv.id::text = d.version_id
    """)).mappings().all()
    for draft in changed_drafts:
        expected = dict(draft["previous_definition"])
        expected.update({"prompt_key": PROMPT_KEY, "identity_key": IDENTITY_KEY})
        if draft["status"] != "DRAFT" or draft["definition"] != expected:
            raise RuntimeError(
                "Cannot downgrade product manifest bootstrap: a migrated media draft changed after migration."
            )

    for row in created:
        bind.execute(sa.text("DELETE FROM production_product_versions WHERE id::text = :id"), {"id": row["product_version_id"]})
        bind.execute(sa.text("""
            UPDATE production_product_versions SET status = 'PUBLISHED' WHERE id::text = :id
        """), {"id": row["previous_version_id"]})
    for draft in changed_drafts:
        bind.execute(sa.text("""
            UPDATE production_product_versions SET definition = CAST(:definition AS JSONB)
            WHERE id::text = :id
        """), {"id": draft["version_id"], "definition": json.dumps(draft["previous_definition"], ensure_ascii=False)})

    bind.execute(sa.text("DELETE FROM editorial_identity_versions WHERE id = :id"), {"id": IDENTITY_VERSION_ID})
    bind.execute(sa.text("DELETE FROM editorial_identities WHERE id = :id"), {"id": IDENTITY_ID})
    op.drop_table("product_manifest_bootstrap_drafts")
    op.drop_table("product_manifest_bootstrap_versions")
