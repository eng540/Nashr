"""Dormant Page attempt state. No production executor."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0070_facebook_execution_core'
down_revision='0069_youtube_review_drafts'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('facebook_executions',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id'),nullable=False),
        *[sa.Column(name,sa.String(length),nullable=False) for name,length in [('page_id',100),('source_fingerprint',64),('kind',10),('state',40)]],
        sa.Column('copy_version',sa.Integer(),nullable=False),
        sa.Column('message',sa.Text(),nullable=False),
        sa.Column('total_bytes',sa.BigInteger(),nullable=False),
        *[sa.Column(name,sa.String(length),nullable=True) for name,length in [('mime_type',100),('media_sha256',64),('post_id',201),('photo_id',100),('error_code',100)]],
        sa.Column('permalink',sa.Text(),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))

def downgrade():
    op.drop_table('facebook_executions')
