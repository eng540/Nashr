"""Seed an inactive video product until durable storage is configured."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0037_video_product_draft"
down_revision: Union[str, Sequence[str], None] = "0036_video_artifact_recipe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "recipe_key": "BOOK_TO_VIDEO_ARTIFACT",
        "output_contract_key": "VIDEO_ARTIFACT",
        "policy_key": "EDITORIAL_DEFAULT",
        "audience": "Readers of Arabic literature and culture",
        "experience": "A source-grounded short vertical video ready for private human review",
    }
    op.execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000995',
            'ARABIC_LITERATURE_VIDEO',
            'Arabic Literature Video',
            'Produce a source-grounded short video Artifact for independent human review.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000996',
            '00000000-0000-0000-0000-000000000995',
            1, CAST(:definition AS JSONB), 'DRAFT'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_product_versions WHERE id = '00000000-0000-0000-0000-000000000996'"))
    op.execute(sa.text("DELETE FROM production_products WHERE id = '00000000-0000-0000-0000-000000000995'"))
