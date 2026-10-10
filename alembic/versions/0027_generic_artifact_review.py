"""Add a human-review lifecycle for non-Post Artifacts."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_generic_artifact_review"
down_revision: Union[str, Sequence[str], None] = "0026_artifact_job_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("review_status", sa.String(length=30), nullable=True))
    op.add_column("artifacts", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_artifacts_review_status",
        "artifacts",
        "review_status IS NULL OR review_status IN ('DRAFT', 'APPROVED', 'REJECTED')",
    )
    op.execute(sa.text("UPDATE artifacts SET review_status = 'DRAFT' WHERE kind <> 'POST' AND review_status IS NULL"))


def downgrade() -> None:
    op.drop_constraint("ck_artifacts_review_status", "artifacts", type_="check")
    op.drop_column("artifacts", "reviewed_at")
    op.drop_column("artifacts", "review_note")
    op.drop_column("artifacts", "review_status")
