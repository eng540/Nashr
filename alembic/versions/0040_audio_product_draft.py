"""Seed an inactive audio product until durable storage is configured."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0040_audio_product_draft"
down_revision: Union[str, Sequence[str], None] = "0039_audio_artifact_recipe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "recipe_key": "BOOK_TO_AUDIO_ARTIFACT",
        "output_contract_key": "AUDIO_ARTIFACT",
        "policy_key": "EDITORIAL_DEFAULT",
        "audience": "Readers and listeners of Arabic literature and culture",
        "experience": "A source-grounded spoken narration ready for private human review",
    }
    op.execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000001005',
            'ARABIC_LITERATURE_AUDIO',
            'Arabic Literature Audio',
            'Produce a source-grounded narration audio Artifact for independent human review.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000001006',
            '00000000-0000-0000-0000-000000001005',
            1, CAST(:definition AS JSONB), 'DRAFT'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_product_versions WHERE id = '00000000-0000-0000-0000-000000001006'"))
    op.execute(sa.text("DELETE FROM production_products WHERE id = '00000000-0000-0000-0000-000000001005'"))
