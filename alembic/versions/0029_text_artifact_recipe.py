"""Seed a recipe that produces a generic TEXT Artifact."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0029_text_artifact_recipe"
down_revision: Union[str, Sequence[str], None] = "0028_seed_text_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000961',
            'BOOK_TO_TEXT_ARTIFACT',
            'Book to Text Artifact',
            'Generate source-grounded inline text without creating a Post row.'
        )
    """))
    definition = {
        "stages": [{
            "key": "generate-text-artifact",
            "capability_key": "produce_text_artifact",
            "capability_version": 1,
            "configuration": {
                "style_instructions": "اكتب نصًا عربيًا واضحًا ومتماسكًا مستندًا إلى المادة المصدرية، دون اختلاق معلومات."
            },
        }]
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000962',
            '00000000-0000-0000-0000-000000000961',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = '00000000-0000-0000-0000-000000000962'"))
    op.execute(sa.text("DELETE FROM production_recipes WHERE id = '00000000-0000-0000-0000-000000000961'"))
