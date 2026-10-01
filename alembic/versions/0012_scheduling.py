"""Add durable schedules and schedule items."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012_scheduling"
down_revision: Union[str, Sequence[str], None] = "0011_production_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_schedules_status", "schedules", ["status"])

    op.create_table(
        "schedule_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("schedule_id", "position", name="uq_schedule_items_schedule_position"),
        sa.UniqueConstraint("schedule_id", "post_id", name="uq_schedule_items_schedule_post"),
    )
    op.create_index("ix_schedule_items_schedule_id", "schedule_items", ["schedule_id"])
    op.create_index("ix_schedule_items_due", "schedule_items", ["status", "scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_schedule_items_due", table_name="schedule_items")
    op.drop_index("ix_schedule_items_schedule_id", table_name="schedule_items")
    op.drop_table("schedule_items")
    op.drop_index("ix_schedules_status", table_name="schedules")
    op.drop_table("schedules")
