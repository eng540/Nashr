"""Add product-versioned presentation instructions to the built-in Arabic text product."""
from __future__ import annotations

import json
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "0047_text_presentation"
down_revision: Union[str, Sequence[str], None] = "0046_media_stage_prompts"
branch_labels = None
depends_on = None


TEXT_PRESENTATION_INSTRUCTIONS = """تعليمات العرض الخاصة بهذا المنتج — تخص شكل النص النهائي ولا تغيّر المصدر أو الهوية أو السياسة:

- اجعل القراءة مريحة على الهاتف: افصل بين الفقرات عند انتقال المعنى بسطر فارغ واحد.
- لا تترك نصًا متعدد الأفكار في كتلة واحدة متصلة، ولا تحوّل كل جملة إلى سطر مستقل.
- حافظ على الأبيات الشعرية والعبارات المتماسكة كما يناسب بنيتها؛ لا تكسرها آليًا.
- لا تضف عنوانًا أو افتتاحية جاذبة أو خلاصة تعليمية إلا إذا كان للمادة سبب تحريري واضح.
- لا تستخدم عناوين Markdown مثل # أو فواصل زخرفية مثل --- أو HTML؛ يُرسل هذا المنتج كنص عادي إلى Telegram.
- استخدم النقاط فقط عندما تكون القائمة هي الشكل الأنسب، وحافظ على نسبة النص إلى قائله.
- اجعل الفراغات والتقسيم تخدم القراءة لا الزخرفة؛ إذا كان الأصل أفضل كما هو، فلا تفرض تنسيقًا زائدًا."""


def upgrade() -> None:
    op.create_table(
        "text_presentation_product_versions",
        sa.Column("product_version_id", sa.String(length=36), primary_key=True),
        sa.Column("previous_version_id", sa.String(length=36), nullable=False),
    )
    bind = op.get_bind()
    active = bind.execute(sa.text("""
        SELECT p.id AS product_id, pv.id AS product_version_id, pv.version, pv.definition
        FROM production_products p
        JOIN production_product_versions pv ON pv.product_id = p.id
        WHERE p.key = 'ARABIC_LITERATURE_TEXT' AND pv.status = 'PUBLISHED'
    """)).mappings().one_or_none()
    if active is None:
        return

    definition = json.loads(json.dumps(active["definition"]))
    if definition.get("output_contract_key") != "TEXT_ARTIFACT":
        return
    if isinstance(definition.get("presentation_instructions"), str) and definition["presentation_instructions"].strip():
        return

    definition["presentation_instructions"] = TEXT_PRESENTATION_INSTRUCTIONS
    latest = bind.execute(sa.text("""
        SELECT COALESCE(MAX(version), 0) FROM production_product_versions WHERE product_id = :product_id
    """), {"product_id": active["product_id"]}).scalar_one()
    new_version_id = uuid4()
    bind.execute(sa.text("""
        UPDATE production_product_versions SET status = 'ARCHIVED'
        WHERE id = CAST(:id AS UUID) AND status = 'PUBLISHED'
    """), {"id": active["product_version_id"]})
    bind.execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (:id, :product_id, :version, CAST(:definition AS JSONB), 'PUBLISHED')
    """), {
        "id": new_version_id,
        "product_id": active["product_id"],
        "version": int(latest) + 1,
        "definition": json.dumps(definition, ensure_ascii=False),
    })
    bind.execute(sa.text("""
        INSERT INTO text_presentation_product_versions (product_version_id, previous_version_id)
        VALUES (:new_id, :previous_id)
    """), {"new_id": str(new_version_id), "previous_id": str(active["product_version_id"])})


def downgrade() -> None:
    bind = op.get_bind()
    changes = bind.execute(sa.text("""
        SELECT product_version_id, previous_version_id
        FROM text_presentation_product_versions
    """)).mappings().all()

    for change in changes:
        new_version = bind.execute(sa.text("""
            SELECT id, product_id, version, status
            FROM production_product_versions
            WHERE id = CAST(:id AS UUID)
        """), {"id": change["product_version_id"]}).mappings().one_or_none()
        if new_version is None or new_version["status"] != "PUBLISHED":
            raise RuntimeError("Cannot downgrade text presentation migration: the generated product version is no longer active.")
        later_version = bind.execute(sa.text("""
            SELECT 1 FROM production_product_versions
            WHERE product_id = :product_id AND version > :version
            LIMIT 1
        """), {"product_id": new_version["product_id"], "version": new_version["version"]}).scalar_one_or_none()
        referenced = bind.execute(sa.text("""
            SELECT 1 FROM production_jobs
            WHERE resolved_context->'product'->>'version_id' = :version_id
            UNION ALL
            SELECT 1 FROM production_products
            WHERE derived_from_version_id = CAST(:version_id AS UUID)
            LIMIT 1
        """), {"version_id": change["product_version_id"]}).scalar_one_or_none()
        if later_version is not None or referenced is not None:
            raise RuntimeError("Cannot downgrade text presentation migration: the product version has been used or superseded.")

    for change in changes:
        bind.execute(sa.text("DELETE FROM production_product_versions WHERE id = CAST(:id AS UUID)"), {"id": change["product_version_id"]})
        bind.execute(sa.text("UPDATE production_product_versions SET status = 'PUBLISHED' WHERE id = CAST(:id AS UUID)"), {"id": change["previous_version_id"]})
    op.drop_table("text_presentation_product_versions")
