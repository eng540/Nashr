"""Telegram local lifecycle and explicit legacy binding, no automatic provider calls."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0061_connection_lifecycle'
down_revision='0060_instagram_oauth'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('managed_connections',sa.Column('enabled',sa.Boolean,nullable=False,server_default=sa.true()))
    op.add_column('managed_connections',sa.Column('last_check_ok',sa.Boolean,nullable=False,server_default=sa.true()))
    op.add_column('managed_connections',sa.Column('last_check_at',sa.DateTime(timezone=True),nullable=True))
    op.create_table('legacy_telegram_binding',sa.Column('id',sa.Integer,primary_key=True),sa.Column('connection_id',pg.UUID(as_uuid=True),sa.ForeignKey('managed_connections.id'),nullable=False),sa.Column('original_destination',sa.String(500),nullable=False))

def downgrade():
    op.drop_table('legacy_telegram_binding')
    op.drop_column('managed_connections','last_check_at')
    op.drop_column('managed_connections','last_check_ok')
    op.drop_column('managed_connections','enabled')
