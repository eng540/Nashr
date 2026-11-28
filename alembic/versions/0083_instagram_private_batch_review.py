"""Private exact batch review snapshots only, no dispatch relationship."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0083_ig_private_batch_review'
down_revision='0082_instagram_batch_drafts'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_private_batch_reviews',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('request_key',sa.String(100),nullable=False,unique=True),
        sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),
        sa.Column('snapshot',pg.JSONB(),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("state IN ('DRAFT','CANCELLED')",name='ck_instagram_private_batch_review_state'))

def downgrade():
    op.drop_table('instagram_private_batch_reviews')
