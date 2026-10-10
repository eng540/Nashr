"""Persist declarative, versioned production policies."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0022_prod_policy_cp"
down_revision: Union[str, Sequence[str], None] = "0021_output_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_production_policies_key"),
    )
    op.create_table(
        "production_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_production_policy_versions_positive_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_production_policy_versions_status"),
        sa.ForeignKeyConstraint(["policy_id"], ["production_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "version", name="uq_production_policy_versions_policy_version"),
    )
    op.create_index("ix_production_policy_versions_policy_id", "production_policy_versions", ["policy_id"])
    op.create_index(
        "uq_production_policy_versions_published",
        "production_policy_versions",
        ["policy_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_production_policy_versions_published", table_name="production_policy_versions")
    op.drop_index("ix_production_policy_versions_policy_id", table_name="production_policy_versions")
    op.drop_table("production_policy_versions")
    op.drop_table("production_policies")
