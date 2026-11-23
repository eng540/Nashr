"""Add storage-backed Telegram media kinds without changing existing rows."""
from alembic import op
revision = "0052_telegram_media_kinds"
down_revision = "0051_quiz_publication"
branch_labels = None
depends_on = None

def upgrade():
    op.drop_constraint("ck_artifacts_kind", "artifacts", type_="check")
    op.create_check_constraint("ck_artifacts_kind", "artifacts", "kind IN ('POST','TEXT','IMAGE','VIDEO','AUDIO','QUIZ','DOCUMENT','ANIMATION','VOICE','VIDEO_NOTE','STICKER')")

def downgrade():
    # Refuse downgrade while new kinds exist; no data is deleted or relabelled.
    op.drop_constraint("ck_artifacts_kind", "artifacts", type_="check")
    op.create_check_constraint("ck_artifacts_kind", "artifacts", "kind IN ('POST','TEXT','IMAGE','VIDEO','AUDIO','QUIZ')")
