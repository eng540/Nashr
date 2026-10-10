"""Seed the inline TEXT output contract."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0028_seed_text_artifact"
down_revision: Union[str, Sequence[str], None] = "0027_generic_artifact_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "artifact_kind": "TEXT",
        "mime_type": "text/plain",
        "content_mode": "INLINE",
        "required_metadata_fields": ["title"],
        "max_content_chars": 100000,
    }
    op.execute(sa.text("""
        INSERT INTO output_contracts (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000951',
            'TEXT_ARTIFACT',
            'Text Artifact',
            'Inline text output persisted and reviewed independently from Post.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO output_contract_versions (id, contract_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000952',
            '00000000-0000-0000-0000-000000000951',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM output_contract_versions WHERE id = '00000000-0000-0000-0000-000000000952'"))
    op.execute(sa.text("DELETE FROM output_contracts WHERE id = '00000000-0000-0000-0000-000000000951'"))
