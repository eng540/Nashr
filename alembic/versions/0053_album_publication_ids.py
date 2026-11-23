"""Preserve every message id returned by an album."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0053_album_publication_ids'
down_revision = '0052_telegram_media_kinds'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('publications', sa.Column('external_ids', postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column('publications', 'external_ids')
