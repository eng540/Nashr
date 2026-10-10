"""Seed the image product as DRAFT until durable storage is configured."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0033_seed_image_product_draft"
down_revision: Union[str, Sequence[str], None] = "0032_image_artifact_recipe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "recipe_key": "BOOK_TO_IMAGE_ARTIFACT",
        "output_contract_key": "IMAGE_ARTIFACT",
        "policy_key": "EDITORIAL_DEFAULT",
        "audience": "Readers of Arabic literature and culture",
        "experience": "An original, source-grounded visual ready for human review",
    }
    op.execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000993',
            'ARABIC_LITERATURE_IMAGE',
            'Arabic Literature Image',
            'Create a source-grounded visual Artifact for independent review.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000994',
            '00000000-0000-0000-0000-000000000993',
            1, CAST(:definition AS JSONB), 'DRAFT'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_product_versions WHERE id = '00000000-0000-0000-0000-000000000994'"))
    op.execute(sa.text("DELETE FROM production_products WHERE id = '00000000-0000-0000-0000-000000000993'"))
