"""Private YouTube preparation snapshots, no upload or execution consent."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0069_youtube_review_drafts"
down_revision = "0068_youtube_upload_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "youtube_review_drafts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "artifact_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id"),
            nullable=False,
        ),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", pg.JSONB(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_youtube_review_drafts_artifact_id", "youtube_review_drafts", ["artifact_id"]
    )


def downgrade():
    op.drop_index(
        "ix_youtube_review_drafts_artifact_id", table_name="youtube_review_drafts"
    )
    op.drop_table("youtube_review_drafts")
