"""Separate durable production claims from execution jobs.

Only jobs with persisted request idempotency metadata receive a migrated claim.
Legacy jobs without that evidence remain claim_id=NULL rather than receiving
fabricated historical claims or reconstructed request fingerprints.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0042_separate_production_claim"
down_revision: Union[str, Sequence[str], None] = "0041_production_claim_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_production_claims_idempotency_key"),
    )

    # Backfill only jobs that already carry a durable replay key AND fingerprint.
    # The generated claim UUID is deliberately distinct from the job UUID.
    op.execute(
        sa.text("""
            INSERT INTO production_claims
                (id, source_id, scope, idempotency_key, request_fingerprint, request_payload, created_at)
            SELECT gen_random_uuid(), source_id, scope, idempotency_key, request_fingerprint,
                   NULL, created_at
            FROM production_jobs
            WHERE idempotency_key IS NOT NULL
              AND request_fingerprint IS NOT NULL
        """)
    )

    op.add_column(
        "production_jobs",
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("production_claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_production_jobs_claim_id", "production_jobs", ["claim_id"], unique=False)
    op.execute(
        sa.text("""
            UPDATE production_jobs AS job
            SET claim_id = claim.id
            FROM production_claims AS claim
            WHERE job.idempotency_key = claim.idempotency_key
              AND job.request_fingerprint = claim.request_fingerprint
        """)
    )
    op.create_unique_constraint("uq_production_jobs_claim_id", "production_jobs", ["claim_id"])
    op.drop_constraint("uq_production_jobs_idempotency_key", "production_jobs", type_="unique")
    op.drop_column("production_jobs", "request_fingerprint")
    op.drop_column("production_jobs", "idempotency_key")


def downgrade() -> None:
    # Preserve replay metadata when possible. Legacy claims without an exact
    # reconstructed request payload still retain their persisted fingerprint.
    op.add_column("production_jobs", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.add_column("production_jobs", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_production_jobs_idempotency_key", "production_jobs", ["idempotency_key"])
    op.execute(
        sa.text("""
            UPDATE production_jobs AS job
            SET idempotency_key = claim.idempotency_key,
                request_fingerprint = claim.request_fingerprint
            FROM production_claims AS claim
            WHERE job.claim_id = claim.id
        """)
    )
    op.drop_constraint("uq_production_jobs_claim_id", "production_jobs", type_="unique")
    op.drop_index("ix_production_jobs_claim_id", table_name="production_jobs")
    op.drop_column("production_jobs", "claim_id")
    op.drop_table("production_claims")
