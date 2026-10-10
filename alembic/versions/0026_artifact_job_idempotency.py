"""Make generic Artifact persistence idempotent per production item."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_artifact_job_idempotency"
down_revision: Union[str, Sequence[str], None] = "0025_product_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_artifacts_job_source_kind",
        "artifacts",
        ["production_job_id", "source_knowledge_unit_id", "kind"],
        unique=True,
        postgresql_where=sa.text("production_job_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_artifacts_job_source_kind", table_name="artifacts")
