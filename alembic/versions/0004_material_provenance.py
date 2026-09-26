"""Add material provenance fields to knowledge units."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_material_provenance"
down_revision: Union[str, Sequence[str], None] = "0003_create_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Store optional original text and source location returned by discovery."""
    op.add_column("knowledge_units", sa.Column("original_text", sa.Text(), nullable=True))
    op.add_column("knowledge_units", sa.Column("source_reference", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    """Remove material provenance fields."""
    op.drop_column("knowledge_units", "source_reference")
    op.drop_column("knowledge_units", "original_text")
