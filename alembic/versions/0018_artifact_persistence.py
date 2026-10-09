"""Persist generic artifacts and link production items to their outputs."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0018_artifact_persistence"
down_revision: Union[str, Sequence[str], None] = "0017_resolved_production_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_knowledge_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="AVAILABLE", nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("storage_uri", sa.String(length=2000), nullable=True),
        sa.Column("mime_type", sa.String(length=200), nullable=True),
        sa.Column("output_contract_key", sa.String(length=200), nullable=True),
        sa.Column("output_contract_version", sa.Integer(), nullable=True),
        sa.Column("production_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('POST', 'TEXT', 'IMAGE', 'VIDEO', 'AUDIO')", name="ck_artifacts_kind"),
        sa.CheckConstraint("status IN ('AVAILABLE', 'FAILED', 'ARCHIVED')", name="ck_artifacts_status"),
        sa.CheckConstraint("kind <> 'POST' OR post_id IS NOT NULL", name="ck_artifacts_post_reference"),
        sa.ForeignKeyConstraint(["source_knowledge_unit_id"], ["knowledge_units.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_job_id"], ["production_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", name="uq_artifacts_post_id"),
    )
    op.create_index("ix_artifacts_source_knowledge_unit_id", "artifacts", ["source_knowledge_unit_id"])
    op.create_index("ix_artifacts_production_job_id", "artifacts", ["production_job_id"])
    op.add_column(
        "production_job_items",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_production_job_items_artifact_id_artifacts",
        "production_job_items",
        "artifacts",
        ["artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_production_job_items_artifact_id", "production_job_items", ["artifact_id"])

    # Every existing Post remains canonical for its editorial content/status.
    # Artifact rows reference that Post rather than duplicating mutable text/status.
    op.execute(sa.text("""
        INSERT INTO artifacts (
            id, source_knowledge_unit_id, kind, status, post_id,
            production_job_id, resolved_context, created_at, updated_at
        )
        SELECT
            post.id,
            post.knowledge_unit_id,
            'POST',
            'AVAILABLE',
            post.id,
            provenance.job_id,
            provenance.resolved_context,
            post.created_at,
            post.updated_at
        FROM posts AS post
        LEFT JOIN LATERAL (
            SELECT job.id AS job_id, job.resolved_context
            FROM production_job_items AS item
            JOIN production_jobs AS job ON job.id = item.job_id
            WHERE item.post_id = post.id
              AND (
                  SELECT count(*)
                  FROM production_job_items AS candidate
                  WHERE candidate.post_id = post.id
              ) = 1
            LIMIT 1
        ) AS provenance ON TRUE
    """))
    op.execute(sa.text("""
        UPDATE production_job_items
        SET artifact_id = post_id
        WHERE post_id IS NOT NULL
    """))


def downgrade() -> None:
    op.drop_index("ix_production_job_items_artifact_id", table_name="production_job_items")
    op.drop_constraint(
        "fk_production_job_items_artifact_id_artifacts",
        "production_job_items",
        type_="foreignkey",
    )
    op.drop_column("production_job_items", "artifact_id")
    op.drop_index("ix_artifacts_production_job_id", table_name="artifacts")
    op.drop_index("ix_artifacts_source_knowledge_unit_id", table_name="artifacts")
    op.drop_table("artifacts")
