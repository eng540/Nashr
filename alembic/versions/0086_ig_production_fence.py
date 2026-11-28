"""Unregistered production fence linkage, no live data initialization."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0086_ig_production_fence'
down_revision='0085_ig_isolated_claim_protocol'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_production_fences',
        sa.Column('dispatch_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_dispatches.id'),sa.ForeignKey('instagram_isolated_controls.dispatch_id'),primary_key=True),
        sa.Column('execution_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_executions.id'),nullable=False,unique=True),
        sa.Column('decision_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_publish_decisions.id'),nullable=False,unique=True),
        sa.Column('grant_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_media_grants.id'),nullable=False,unique=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.execute('CREATE TRIGGER immutable_fence_link BEFORE UPDATE OR DELETE ON instagram_production_fences FOR EACH ROW EXECUTE FUNCTION ig_isolated_immutable()')

def downgrade():
    op.drop_table('instagram_production_fences')
