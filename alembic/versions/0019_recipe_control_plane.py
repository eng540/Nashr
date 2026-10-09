"""Persist versioned production recipe definitions in the Control Plane."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0019_recipe_control_plane"
down_revision: Union[str, Sequence[str], None] = "0018_artifact_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_recipes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_production_recipes_key"),
    )
    op.create_table(
        "production_recipe_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_production_recipe_versions_positive_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_production_recipe_versions_status"),
        sa.ForeignKeyConstraint(["recipe_id"], ["production_recipes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recipe_id", "version", name="uq_production_recipe_versions_recipe_version"),
    )
    op.create_index("ix_production_recipe_versions_recipe_id", "production_recipe_versions", ["recipe_id"])
    op.create_index(
        "uq_production_recipe_versions_published",
        "production_recipe_versions",
        ["recipe_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )
    op.execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000901',
            'BOOK_TO_TELEGRAM_POST',
            'Book to Telegram Post',
            'Produce a reviewed Post artifact from selected book knowledge and prepare it for the existing publication flow.'
        )
    """))
    definition = {
        "stages": [
            {"key": "produce-post", "capability_key": "produce_post", "capability_version": 1}
        ]
    }
    op.execute(
        sa.text("""
            INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
            VALUES (
                '00000000-0000-0000-0000-000000000902',
                '00000000-0000-0000-0000-000000000901',
                1,
                CAST(:definition AS JSONB),
                'PUBLISHED'
            )
        """),
        {"definition": json.dumps(definition)},
    )


def downgrade() -> None:
    op.drop_index("uq_production_recipe_versions_published", table_name="production_recipe_versions")
    op.drop_index("ix_production_recipe_versions_recipe_id", table_name="production_recipe_versions")
    op.drop_table("production_recipe_versions")
    op.drop_table("production_recipes")
