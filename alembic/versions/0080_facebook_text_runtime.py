"""Bind exact public text decisions without activating legacy attempts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0080_facebook_text_runtime'
down_revision='0079_youtube_connection'
branch_labels=None
depends_on=None
def upgrade():
    for c in [sa.Column('runtime_snapshot',pg.JSONB(),nullable=True),sa.Column('runtime_hash',sa.String(64),nullable=True),sa.Column('evidence_ref',sa.Text(),nullable=True),sa.Column('due_at',sa.DateTime(timezone=True),nullable=True),sa.Column('approved_until',sa.DateTime(timezone=True),nullable=True)]:op.add_column('facebook_executions',c)
def downgrade():
    for c in ['approved_until','due_at','evidence_ref','runtime_hash','runtime_snapshot']:op.drop_column('facebook_executions',c)
