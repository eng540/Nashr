"""Create the knowledge_units table."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_create_knowledge_units"
down_revision: Union[str, Sequence[str], None] = "0001_create_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the knowledge_units table."""
    op.create_table(
        "knowledge_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "position", name="uq_knowledge_units_source_position"),
    )


def downgrade() -> None:
    """Drop the knowledge_units table."""
    op.drop_table("knowledge_units")
