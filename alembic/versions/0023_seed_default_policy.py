"""Seed the compatibility-default production policy for new jobs."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0023_seed_default_policy"
down_revision: Union[str, Sequence[str], None] = "0022_prod_policy_cp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "min_content_chars": 1,
        "max_content_chars": 100000,
        "required_terms": [],
        "forbidden_terms": [],
        "allow_urls": True,
    }
    op.execute(sa.text("""
        INSERT INTO production_policies (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000921',
            'EDITORIAL_DEFAULT',
            'Default Editorial Policy',
            'Compatibility policy for the current Post production flow.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO production_policy_versions (id, policy_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000922',
            '00000000-0000-0000-0000-000000000921',
            1,
            CAST(:definition AS JSONB),
            'PUBLISHED'
        )
    """), {"definition": json.dumps(definition)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_policy_versions WHERE id = '00000000-0000-0000-0000-000000000922'"))
    op.execute(sa.text("DELETE FROM production_policies WHERE id = '00000000-0000-0000-0000-000000000921'"))
