"""Dormant pinned resumable upload records, no scheduler or publishing route."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0068_youtube_upload_core"
down_revision = "0067_instagram_plan_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "youtube_uploads",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "artifact_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(100), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("copy_version", sa.Integer(), nullable=False),
        sa.Column("media_sha256", sa.String(64), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("metadata_snapshot", pg.JSONB(), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("session_ciphertext", sa.Text(), nullable=True),
        sa.Column(
            "received_bytes", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("retry_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("video_id", sa.String(20), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_table("youtube_uploads")
