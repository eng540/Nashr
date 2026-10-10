"""Persist versioned production product definitions."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0025_product_control_plane"
down_revision: Union[str, Sequence[str], None] = "0024_seed_brief_recipe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_production_products_key"),
    )
    op.create_table(
        "production_product_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_production_product_versions_positive_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_production_product_versions_status"),
        sa.ForeignKeyConstraint(["product_id"], ["production_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "version", name="uq_production_product_versions_product_version"),
    )
    op.create_index("ix_production_product_versions_product_id", "production_product_versions", ["product_id"])
    op.create_index(
        "uq_production_product_versions_published",
        "production_product_versions",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )
    products = [
        {
            "id": "00000000-0000-0000-0000-000000000941",
            "version_id": "00000000-0000-0000-0000-000000000942",
            "key": "ARABIC_LITERATURE_TELEGRAM_POST",
            "name": "Arabic Literature Telegram Post",
            "purpose": "Create a source-faithful literary post for readers of Arabic literature.",
            "definition": {
                "recipe_key": "BOOK_TO_TELEGRAM_POST",
                "output_contract_key": "TELEGRAM_POST",
                "policy_key": "EDITORIAL_DEFAULT",
                "audience": "Readers of Arabic literature and culture",
                "experience": "A source-grounded post ready for human review and Telegram publication",
            },
        },
        {
            "id": "00000000-0000-0000-0000-000000000943",
            "version_id": "00000000-0000-0000-0000-000000000944",
            "key": "ARABIC_LITERATURE_BRIEF_TELEGRAM_POST",
            "name": "Brief Arabic Literature Telegram Post",
            "purpose": "Create a concise literary post using the shared recipe engine.",
            "definition": {
                "recipe_key": "BOOK_TO_TELEGRAM_POST_BRIEF",
                "output_contract_key": "TELEGRAM_POST",
                "policy_key": "EDITORIAL_DEFAULT",
                "audience": "Readers who prefer concise Arabic literary content",
                "experience": "A concise source-grounded post ready for human review and Telegram publication",
            },
        },
    ]
    for product in products:
        op.get_bind().execute(sa.text("""
            INSERT INTO production_products (id, key, name, purpose)
            VALUES (:id, :key, :name, :purpose)
        """), {k: product[k] for k in ("id", "key", "name", "purpose")})
        op.get_bind().execute(sa.text("""
            INSERT INTO production_product_versions (id, product_id, version, definition, status)
            VALUES (:version_id, :id, 1, CAST(:definition AS JSONB), 'PUBLISHED')
        """), {
            "version_id": product["version_id"],
            "id": product["id"],
            "definition": json.dumps(product["definition"], ensure_ascii=False),
        })


def downgrade() -> None:
    op.drop_index("uq_production_product_versions_published", table_name="production_product_versions")
    op.drop_index("ix_production_product_versions_product_id", table_name="production_product_versions")
    op.drop_table("production_product_versions")
    op.drop_table("production_products")
