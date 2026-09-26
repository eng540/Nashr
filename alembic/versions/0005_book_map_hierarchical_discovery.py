"""Add book map topics and hierarchical material metadata."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_book_map"
down_revision: Union[str, Sequence[str], None] = "0004_material_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("book_title", sa.String(length=500), nullable=True))
    op.add_column("sources", sa.Column("book_description", sa.Text(), nullable=True))
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "position", name="uq_topics_source_position"),
    )
    op.add_column("knowledge_units", sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("knowledge_units", sa.Column("kind", sa.String(length=200), nullable=True))
    op.create_foreign_key("fk_knowledge_units_topic_id", "knowledge_units", "topics", ["topic_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_knowledge_units_topic_id", "knowledge_units", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_units_topic_id", table_name="knowledge_units")
    op.drop_constraint("fk_knowledge_units_topic_id", "knowledge_units", type_="foreignkey")
    op.drop_column("knowledge_units", "kind")
    op.drop_column("knowledge_units", "topic_id")
    op.drop_table("topics")
    op.drop_column("sources", "book_description")
    op.drop_column("sources", "book_title")
