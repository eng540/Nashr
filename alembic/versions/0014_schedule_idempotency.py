"""Add durable schedule creation idempotency keys."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_schedule_idempotency"
down_revision: Union[str, Sequence[str], None] = "0013_editorial_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.create_index(
        "uq_schedules_idempotency_key",
        "schedules",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_schedules_idempotency_key", table_name="schedules")
    op.drop_column("schedules", "idempotency_key")
