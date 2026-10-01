"""Add the persisted editorial Post foundation."""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_post_foundation"
down_revision: Union[str, Sequence[str], None] = "0009_book_map_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("knowledge_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["knowledge_unit_id"], ["knowledge_units.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("knowledge_unit_id", "status", name="uq_posts_knowledge_unit_status"),
    )
    op.create_index("ix_posts_knowledge_unit_id", "posts", ["knowledge_unit_id"])

    op.add_column(
        "publications",
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_publications_post_id_posts",
        "publications",
        "posts",
        ["post_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_publications_post_platform_destination",
        "publications",
        ["post_id", "platform", "destination"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_publications_post_platform_destination", "publications", type_="unique")
    op.drop_constraint("fk_publications_post_id_posts", "publications", type_="foreignkey")
    op.drop_column("publications", "post_id")
    op.drop_index("ix_posts_knowledge_unit_id", table_name="posts")
    op.drop_table("posts")
