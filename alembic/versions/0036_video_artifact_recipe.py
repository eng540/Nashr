"""Seed a resumable Veo-backed video Artifact recipe."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0036_video_artifact_recipe"
down_revision: Union[str, Sequence[str], None] = "0035_seed_video_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000993',
            'BOOK_TO_VIDEO_ARTIFACT',
            'Book to Video Artifact',
            'Generate a short source-grounded video with a resumable provider operation and private storage.'
        )
    """))
    definition = {
        "stages": [{
            "key": "generate-video-artifact",
            "capability_key": "produce_video_artifact",
            "capability_version": 1,
            "configuration": {
                "style_instructions": "أنشئ مقطعاً تحريرياً عمودياً قصيراً يستلهم المعنى من المادة المصدرية، دون كتابة عناوين أو شعارات داخل الفيديو.",
                "aspect_ratio": "9:16",
                "resolution": "720p",
                "duration_seconds": 5,
            },
        }]
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000994',
            '00000000-0000-0000-0000-000000000993',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = '00000000-0000-0000-0000-000000000994'"))
    op.execute(sa.text("DELETE FROM production_recipes WHERE id = '00000000-0000-0000-0000-000000000993'"))
