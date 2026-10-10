"""Persist external provider operation handles for resumable production items."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034_provider_operation_state"
down_revision: Union[str, Sequence[str], None] = "0033_image_product_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("production_job_items", sa.Column("provider_name", sa.String(length=100), nullable=True))
    op.add_column("production_job_items", sa.Column("provider_operation_name", sa.String(length=500), nullable=True))
    op.add_column("production_job_items", sa.Column("provider_operation_status", sa.String(length=30), nullable=True))
    op.add_column("production_job_items", sa.Column("provider_operation_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_production_job_items_provider_operation_state",
        "production_job_items",
        "("
        "(provider_name IS NULL AND provider_operation_name IS NULL AND provider_operation_status IS NULL) "
        "OR "
        "(provider_name IS NOT NULL AND provider_operation_name IS NOT NULL "
        "AND provider_operation_status IN ('SUBMITTED', 'RUNNING', 'SUCCEEDED', 'FAILED'))"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_production_job_items_provider_operation_state",
        "production_job_items",
        type_="check",
    )
    op.drop_column("production_job_items", "provider_operation_updated_at")
    op.drop_column("production_job_items", "provider_operation_status")
    op.drop_column("production_job_items", "provider_operation_name")
    op.drop_column("production_job_items", "provider_name")
