"""Pin direct connection provenance on private execution drafts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0074_instagram_execution_binding'
down_revision='0073_instagram_direct_login'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('instagram_executions',sa.Column('connection_binding',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))

def downgrade():
    op.drop_column('instagram_executions','connection_binding')
