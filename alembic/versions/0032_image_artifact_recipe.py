"""Seed the Gemini-backed image artifact recipe."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0032_image_artifact_recipe"
down_revision: Union[str, Sequence[str], None] = "0031_seed_image_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000991',
            'BOOK_TO_IMAGE_ARTIFACT',
            'Book to Image Artifact',
            'Generate a source-grounded image and persist it as a reviewable Artifact.'
        )
    """))
    definition = {
        "stages": [{
            "key": "generate-image-artifact",
            "capability_key": "produce_image_artifact",
            "capability_version": 1,
            "configuration": {
                "style_instructions": "استخدم استعارة بصرية أصيلة وأنيقة تلائم الأدب والثقافة العربية، دون كتابة كلمات داخل الصورة."
            },
        }]
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000992',
            '00000000-0000-0000-0000-000000000991',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = '00000000-0000-0000-0000-000000000992'"))
    op.execute(sa.text("DELETE FROM production_recipes WHERE id = '00000000-0000-0000-0000-000000000991'"))
