"""Dormant private batch proposal storage. No route or worker consumes this table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0082_instagram_batch_drafts'
down_revision='0081_tiktok_inbox_consent'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_batch_drafts',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('request_key',sa.String(100),nullable=False,unique=True),
        sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),
        sa.Column('snapshot',pg.JSONB(),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),
        sa.Column('decision_ids',pg.JSONB(),nullable=False),
        sa.Column('evidence_ref',sa.Text(),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('approved_at',sa.DateTime(timezone=True),nullable=True),
        sa.CheckConstraint("state IN ('DRAFT','APPROVED')",name='ck_instagram_batch_draft_state'))

def downgrade():
    op.drop_table('instagram_batch_drafts')
