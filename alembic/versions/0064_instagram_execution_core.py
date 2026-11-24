"""Persist Instagram execution attempts without activating a publish route."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0064_instagram_execution_core'
down_revision='0063_copy_suggestions'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_executions',sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id'),nullable=False),sa.Column('account_id',sa.String(100),nullable=False),sa.Column('source_fingerprint',sa.String(64),nullable=False),sa.Column('copy_version',sa.Integer,nullable=False),sa.Column('media_sha256',sa.String(64),nullable=False),sa.Column('kind',sa.String(10),nullable=False),sa.Column('caption',sa.Text,nullable=False),sa.Column('alt_text',sa.Text,nullable=False),sa.Column('share_to_feed',sa.Boolean,nullable=True),sa.Column('state',sa.String(40),nullable=False),sa.Column('container_id',sa.String(100),nullable=True),sa.Column('media_id',sa.String(100),nullable=True),sa.Column('error_code',sa.String(100),nullable=True),sa.Column('permalink',sa.Text,nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():op.drop_table('instagram_executions')
