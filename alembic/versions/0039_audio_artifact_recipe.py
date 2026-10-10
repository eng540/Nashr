"""Seed a Gemini TTS recipe for source-grounded audio narration."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0039_audio_artifact_recipe"
down_revision: Union[str, Sequence[str], None] = "0038_seed_audio_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000001003',
            'BOOK_TO_AUDIO_ARTIFACT',
            'Book to Audio Artifact',
            'Draft a source-grounded narration script and synthesize it as private audio.'
        )
    """))
    definition = {
        "stages": [{
            "key": "generate-audio-artifact",
            "capability_key": "produce_audio_artifact",
            "capability_version": 1,
            "configuration": {
                "style_instructions": "اكتب نصاً عربياً أدبياً أميناً للمادة المصدرية، مناسباً للإلقاء الصوتي الواضح دون مبالغة أو إضافة معلومات غير موجودة.",
                "voice": "Kore",
                "speech_style": "Arabic literary narration, warm, clear, measured pace",
            },
        }]
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000001004',
            '00000000-0000-0000-0000-000000001003',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = '00000000-0000-0000-0000-000000001004'"))
    op.execute(sa.text("DELETE FROM production_recipes WHERE id = '00000000-0000-0000-0000-000000001003'"))
