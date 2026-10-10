"""Seed the storage-backed VIDEO output contract."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0035_seed_video_artifact"
down_revision: Union[str, Sequence[str], None] = "0034_provider_operation_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "artifact_kind": "VIDEO",
        "mime_type": "video/mp4",
        "content_mode": "STORAGE_URI",
        "required_metadata_fields": ["title"],
        "max_content_chars": None,
    }
    op.execute(sa.text("""
        INSERT INTO output_contracts (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000991',
            'VIDEO_ARTIFACT',
            'Video Artifact',
            'Private, storage-backed video output with a durable provider-operation record.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO output_contract_versions (id, contract_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000992',
            '00000000-0000-0000-0000-000000000991',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM output_contract_versions WHERE id = '00000000-0000-0000-0000-000000000992'"))
    op.execute(sa.text("DELETE FROM output_contracts WHERE id = '00000000-0000-0000-0000-000000000991'"))
