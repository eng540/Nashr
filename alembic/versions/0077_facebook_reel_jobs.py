"""Exact Facebook Reel owner decision and durable no-replay lifecycle."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0077_facebook_reel_jobs'
down_revision='0076_facebook_page_connection'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('facebook_reel_jobs',sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id'),nullable=False),sa.Column('snapshot',pg.JSONB(),nullable=False),sa.Column('snapshot_hash',sa.String(64),nullable=False),sa.Column('state',sa.String(40),nullable=False),sa.Column('evidence_ref',sa.Text()),sa.Column('approved_until',sa.DateTime(timezone=True)),sa.Column('remote_session',pg.JSONB()),sa.Column('permalink',sa.Text()),sa.Column('error_code',sa.String(100)),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():op.drop_table('facebook_reel_jobs')
