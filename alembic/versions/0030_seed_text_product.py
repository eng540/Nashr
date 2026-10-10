"""Seed the first user-selectable generic text product."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0030_seed_text_product"
down_revision: Union[str, Sequence[str], None] = "0029_text_artifact_recipe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "recipe_key": "BOOK_TO_TEXT_ARTIFACT",
        "output_contract_key": "TEXT_ARTIFACT",
        "policy_key": "EDITORIAL_DEFAULT",
        "audience": "Readers of Arabic literature and culture",
        "experience": "A source-grounded text artifact ready for independent human review",
    }
    op.execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000971',
            'ARABIC_LITERATURE_TEXT',
            'Arabic Literature Text',
            'Produce reviewable text artifacts independent of the Post publication path.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000972',
            '00000000-0000-0000-0000-000000000971',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_product_versions WHERE id = '00000000-0000-0000-0000-000000000972'"))
    op.execute(sa.text("DELETE FROM production_products WHERE id = '00000000-0000-0000-0000-000000000971'"))
