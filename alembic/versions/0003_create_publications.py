"""Create the publications table."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_create_publications"
down_revision: Union[str, Sequence[str], None] = "0002_create_knowledge_units"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create the publications table."""
    op.create_table(
        "publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("knowledge_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False, server_default="telegram"),
        sa.Column("destination", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="DRAFT"),
        sa.Column("external_id", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["knowledge_unit_id"], ["knowledge_units.id"], ondelete="RESTRICT"),
    )

def downgrade() -> None:
    """Drop the publications table."""
    op.drop_table("publications")
