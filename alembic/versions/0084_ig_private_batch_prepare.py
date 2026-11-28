"""Dormant private preparation receipts, no routes or runnable work."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0084_ig_private_batch_prepare'
down_revision='0083_ig_private_batch_review'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_private_batch_preparations',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('review_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_private_batch_reviews.id'),nullable=False,unique=True),
        sa.Column('request_key',sa.String(100),nullable=False,unique=True),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),
        sa.Column('items',pg.JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():op.drop_table('instagram_private_batch_preparations')
