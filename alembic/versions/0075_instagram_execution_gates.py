"""Dormant exact decisions, revocable capabilities and due-time claims."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0075_instagram_execution_gates'
down_revision='0074_instagram_execution_binding'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_publish_decisions',sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('execution_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_executions.id'),nullable=False),sa.Column('snapshot_hash',sa.String(64),nullable=False),sa.Column('snapshot',pg.JSONB(),nullable=False),sa.Column('evidence_ref',sa.Text(),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_instagram_publish_decisions_execution_id','instagram_publish_decisions',['execution_id'])
    op.create_table('instagram_media_grants',sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('execution_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_executions.id'),nullable=False),sa.Column('decision_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_publish_decisions.id'),nullable=False),sa.Column('capability_hash',sa.String(64),nullable=False,unique=True),sa.Column('sha256',sa.String(64),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('reads',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_instagram_media_grants_execution_id','instagram_media_grants',['execution_id'])
    op.create_table('instagram_dispatches',sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('execution_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_executions.id'),nullable=False,unique=True),sa.Column('decision_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_publish_decisions.id'),nullable=False),sa.Column('due_at',sa.DateTime(timezone=True),nullable=False),sa.Column('state',sa.String(30),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    op.drop_table('instagram_dispatches');op.drop_table('instagram_media_grants');op.drop_table('instagram_publish_decisions')
