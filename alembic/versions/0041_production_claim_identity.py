"""Add explicit production claim identity and permit independent posts per job."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0041_production_claim_identity"
down_revision: Union[str, Sequence[str], None] = "0040_audio_product_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("production_jobs", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.add_column("production_jobs", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        "uq_production_jobs_idempotency_key", "production_jobs", ["idempotency_key"]
    )

    op.add_column(
        "posts",
        sa.Column(
            "production_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("production_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_constraint("uq_posts_knowledge_unit", "posts", type_="unique")
    op.create_unique_constraint(
        "uq_posts_job_knowledge_unit", "posts", ["production_job_id", "knowledge_unit_id"]
    )


def downgrade() -> None:
    # Re-create the legacy constraint only when the data satisfies it. A downgrade
    # must not silently delete or merge posts created after this migration.
    op.drop_constraint("uq_posts_job_knowledge_unit", "posts", type_="unique")
    op.drop_column("posts", "production_job_id")
    op.create_unique_constraint("uq_posts_knowledge_unit", "posts", ["knowledge_unit_id"])
    op.drop_constraint("uq_production_jobs_idempotency_key", "production_jobs", type_="unique")
    op.drop_column("production_jobs", "request_fingerprint")
    op.drop_column("production_jobs", "idempotency_key")
