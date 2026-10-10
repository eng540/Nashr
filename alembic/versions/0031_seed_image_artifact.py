"""Seed the storage-backed IMAGE output contract."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0031_seed_image_artifact"
down_revision: Union[str, Sequence[str], None] = "0030_seed_text_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "artifact_kind": "IMAGE",
        "mime_type": "image/png",
        "content_mode": "STORAGE_URI",
        "required_metadata_fields": ["title", "alt_text"],
        "max_content_chars": None,
    }
    op.execute(sa.text("""
        INSERT INTO output_contracts (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000981',
            'IMAGE_ARTIFACT',
            'Image Artifact',
            'Storage-backed editorial image with required title and alternative text.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO output_contract_versions (id, contract_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000982',
            '00000000-0000-0000-0000-000000000981',
            1, CAST(:definition AS JSONB), 'PUBLISHED'
        )
    """), {"definition": json.dumps(definition)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM output_contract_versions WHERE id = '00000000-0000-0000-0000-000000000982'"))
    op.execute(sa.text("DELETE FROM output_contracts WHERE id = '00000000-0000-0000-0000-000000000981'"))
