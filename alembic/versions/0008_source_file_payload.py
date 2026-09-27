"""Add file_payload to sources for persistent binary storage.

Revision ID: 0008_source_file_payload
Revises: 0007_bounded_discovery
Create Date: 2026-09-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_source_file_payload"
down_revision: Union[str, Sequence[str], None] = "0007_bounded_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add file_payload column to store PDF bytes directly in PostgreSQL."""
    op.add_column("sources", sa.Column("file_payload", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    """Remove file_payload column."""
    op.drop_column("sources", "file_payload")
