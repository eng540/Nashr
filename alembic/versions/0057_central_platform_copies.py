"""Linked platform preparation records, no content mutation or publish authority."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0057_central_platform_copies'
down_revision='0056_telegram_batch_review'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('platform_copies',
        sa.Column('artifact_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('artifacts.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('platform',sa.String(30),primary_key=True),
        sa.Column('source_fingerprint',sa.String(64),nullable=False),
        sa.Column('fields',postgresql.JSONB(),nullable=False),
        sa.Column('origin',sa.String(30),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False,server_default='1'),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))

def downgrade():
    op.drop_table('platform_copies')
