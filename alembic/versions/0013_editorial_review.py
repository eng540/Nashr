"""Add durable editorial review metadata to posts."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_editorial_review"
down_revision: Union[str, Sequence[str], None] = "0012_scheduling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("posts", sa.Column("review_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "review_note")
    op.drop_column("posts", "reviewed_at")
