"""Seed a second recipe using the shared engine and bounded stage configuration."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0024_seed_brief_recipe"
down_revision: Union[str, Sequence[str], None] = "0023_seed_default_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000931',
            'BOOK_TO_TELEGRAM_POST_BRIEF',
            'Book to Brief Telegram Post',
            'Produce a concise Telegram Post from book knowledge using the shared production engine.'
        )
    """))
    definition = {
        "stages": [{
            "key": "produce-brief-post",
            "capability_key": "produce_post",
            "capability_version": 1,
            "configuration": {
                "style_instructions": "اكتب منشورًا موجزًا ومكثفًا، مع الحفاظ على الفكرة الأساسية للمادة وعدم اختلاق أي معلومة."
            },
        }]
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000932',
            '00000000-0000-0000-0000-000000000931',
            1,
            CAST(:definition AS JSONB),
            'PUBLISHED'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = '00000000-0000-0000-0000-000000000932'"))
    op.execute(sa.text("DELETE FROM production_recipes WHERE id = '00000000-0000-0000-0000-000000000931'"))
