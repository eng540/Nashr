"""Private bounded in-product agent tasks, no model or publication effects."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0089_nashr_agent_tasks'
down_revision='0088_ig_preclaim_stop'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('nashr_agent_tasks',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('request_key',sa.String(100),nullable=False,unique=True),
        sa.Column('request_text',sa.Text(),nullable=False),
        sa.Column('plan_hash',sa.String(64),nullable=False),
        sa.Column('plan',pg.JSONB(),nullable=False),
        sa.Column('state',sa.String(30),nullable=False),
        sa.Column('cursor',sa.Integer(),nullable=False),
        sa.Column('results',pg.JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():op.drop_table('nashr_agent_tasks')
