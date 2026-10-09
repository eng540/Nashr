"""Persist versioned editorial identities in the Control Plane."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0020_identity_control_plane"
down_revision: Union[str, Sequence[str], None] = "0019_recipe_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editorial_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_editorial_identities_key"),
    )
    op.create_table(
        "editorial_identity_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_editorial_identity_versions_positive_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_editorial_identity_versions_status"),
        sa.ForeignKeyConstraint(["identity_id"], ["editorial_identities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_id", "version", name="uq_editorial_identity_versions_identity_version"),
    )
    op.create_index("ix_editorial_identity_versions_identity_id", "editorial_identity_versions", ["identity_id"])
    op.create_index(
        "uq_editorial_identity_versions_published",
        "editorial_identity_versions",
        ["identity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_editorial_identity_versions_published", table_name="editorial_identity_versions")
    op.drop_index("ix_editorial_identity_versions_identity_id", table_name="editorial_identity_versions")
    op.drop_table("editorial_identity_versions")
    op.drop_table("editorial_identities")
