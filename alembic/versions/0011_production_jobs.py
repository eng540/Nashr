"""Add durable production jobs and job items."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011_production_jobs"
down_revision: Union[str, Sequence[str], None] = "0010_post_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="QUEUED"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_production_jobs_source_id", "production_jobs", ["source_id"])
    op.create_index("ix_production_jobs_status", "production_jobs", ["status"])

    op.create_table(
        "production_job_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["production_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_unit_id"], ["knowledge_units.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("job_id", "knowledge_unit_id", name="uq_production_job_items_job_knowledge_unit"),
        sa.UniqueConstraint("job_id", "position", name="uq_production_job_items_job_position"),
    )
    op.create_index("ix_production_job_items_job_id", "production_job_items", ["job_id"])
    op.create_index("ix_production_job_items_status", "production_job_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_production_job_items_status", table_name="production_job_items")
    op.drop_index("ix_production_job_items_job_id", table_name="production_job_items")
    op.drop_table("production_job_items")
    op.drop_index("ix_production_jobs_status", table_name="production_jobs")
    op.drop_index("ix_production_jobs_source_id", table_name="production_jobs")
    op.drop_table("production_jobs")
