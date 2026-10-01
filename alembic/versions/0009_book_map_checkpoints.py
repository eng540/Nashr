"""Persist bounded Book Map section checkpoints."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_book_map_checkpoints"
down_revision: Union[str, Sequence[str], None] = "0008_source_file_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "book_map_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "section_index", name="uq_book_map_sections_source_index"),
    )
    op.create_index("ix_book_map_sections_source_id", "book_map_sections", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_book_map_sections_source_id", table_name="book_map_sections")
    op.drop_table("book_map_sections")
