"""Add bounded discovery provenance and chunk checkpoints."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_bounded_discovery"
down_revision: Union[str, Sequence[str], None] = "0006_discovery_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("topics", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("topics", sa.Column("page_end", sa.Integer(), nullable=True))
    op.add_column("knowledge_units", sa.Column("discovery_page_start", sa.Integer(), nullable=True))
    op.add_column("knowledge_units", sa.Column("discovery_page_end", sa.Integer(), nullable=True))
    op.add_column("knowledge_units", sa.Column("discovery_chunk_index", sa.Integer(), nullable=True))

    op.create_table(
        "discovery_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("topic_id", "chunk_index", name="uq_discovery_chunks_topic_index"),
    )
    op.create_index("ix_discovery_chunks_topic_id", "discovery_chunks", ["topic_id"])

    op.add_column("discovery_jobs", sa.Column("chunks_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("discovery_jobs", sa.Column("chunks_completed", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("discovery_jobs", sa.Column("current_chunk_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("discovery_jobs", sa.Column("error_code", sa.String(length=80), nullable=True))
    op.create_foreign_key(
        "fk_discovery_jobs_current_chunk",
        "discovery_jobs",
        "discovery_chunks",
        ["current_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_discovery_jobs_current_chunk", "discovery_jobs", type_="foreignkey")
    op.drop_column("discovery_jobs", "error_code")
    op.drop_column("discovery_jobs", "current_chunk_id")
    op.drop_column("discovery_jobs", "chunks_completed")
    op.drop_column("discovery_jobs", "chunks_total")
    op.drop_index("ix_discovery_chunks_topic_id", table_name="discovery_chunks")
    op.drop_table("discovery_chunks")
    op.drop_column("knowledge_units", "discovery_chunk_index")
    op.drop_column("knowledge_units", "discovery_page_end")
    op.drop_column("knowledge_units", "discovery_page_start")
    op.drop_column("topics", "page_end")
    op.drop_column("topics", "page_start")
