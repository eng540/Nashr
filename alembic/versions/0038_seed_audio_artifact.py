"""Seed the storage-backed AUDIO output contract."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0038_seed_audio_artifact"
down_revision: Union[str, Sequence[str], None] = "0037_video_product_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "artifact_kind": "AUDIO",
        "mime_type": "audio/wav",
        "content_mode": "STORAGE_URI",
        "required_metadata_fields": ["title"],
        "max_content_chars": None,
    }
    op.execute(sa.text("""
        INSERT INTO output_contracts (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000001001',
            'AUDIO_ARTIFACT',
            'Audio Artifact',
            'Private, storage-backed narration audio for independent human review.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO output_contract_versions (id, contract_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000001002',
            '00000000-0000-0000-0000-000000001001',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM output_contract_versions WHERE id = '00000000-0000-0000-0000-000000001002'"))
    op.execute(sa.text("DELETE FROM output_contracts WHERE id = '00000000-0000-0000-0000-000000001001'"))
