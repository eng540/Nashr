"""Add durable discovery job state and reusable Gemini document metadata."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_discovery_jobs"
down_revision: Union[str, Sequence[str], None] = "0005_book_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.add_column("sources", sa.Column("gemini_file_name", sa.String(length=500), nullable=True))
    op.add_column("sources", sa.Column("gemini_file_uri", sa.String(length=2000), nullable=True))
    op.add_column("sources", sa.Column("gemini_file_mime_type", sa.String(length=100), nullable=True))
    op.add_column("sources", sa.Column("gemini_file_source_sha256", sa.String(length=64), nullable=True))

    op.add_column(
        "topics",
        sa.Column("discovery_status", sa.String(length=30), nullable=False, server_default="PENDING"),
    )
    op.add_column("topics", sa.Column("discovery_error", sa.Text(), nullable=True))

    op.create_table(
        "discovery_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("topics_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topics_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("materials_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_topic_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_topic_id"], ["topics.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_discovery_jobs_source_id", "discovery_jobs", ["source_id"])
    op.create_index(
        "uq_discovery_jobs_active_source",
        "discovery_jobs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_discovery_jobs_active_source", table_name="discovery_jobs")
    op.drop_index("ix_discovery_jobs_source_id", table_name="discovery_jobs")
    op.drop_table("discovery_jobs")
    op.drop_column("topics", "discovery_error")
    op.drop_column("topics", "discovery_status")
    op.drop_column("sources", "gemini_file_source_sha256")
    op.drop_column("sources", "gemini_file_mime_type")
    op.drop_column("sources", "gemini_file_uri")
    op.drop_column("sources", "gemini_file_name")
    op.drop_column("sources", "content_sha256")
