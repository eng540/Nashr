"""Private Instagram review drafts, not runnable schedules."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0067_instagram_plan_drafts'
down_revision='0066_instagram_media_pin'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_plan_drafts',sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id'),nullable=False),sa.Column('snapshot_hash',sa.String(64),nullable=False),sa.Column('snapshot',pg.JSONB(),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))

def downgrade():op.drop_table('instagram_plan_drafts')
