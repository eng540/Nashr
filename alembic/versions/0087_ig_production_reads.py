"""Unregistered bounded media-read observations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0087_ig_production_reads'
down_revision='0086_ig_production_fence'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_production_reads',
        sa.Column('claim_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_isolated_claims.id'),primary_key=True),
        sa.Column('dispatch_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_production_fences.dispatch_id'),nullable=False),
        sa.Column('control_version',sa.Integer(),nullable=False),
        sa.Column('container_id',sa.String(100),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.execute('CREATE TRIGGER immutable_production_read BEFORE UPDATE OR DELETE ON instagram_production_reads FOR EACH ROW EXECUTE FUNCTION ig_isolated_immutable()')

def downgrade():op.drop_table('instagram_production_reads')
