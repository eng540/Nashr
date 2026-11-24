"""Owner-driven Instagram OAuth, separate from publication."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0060_instagram_oauth'
down_revision='0059_media_inspections'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_oauth_flows',
        sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('session_hash',sa.String(64),nullable=False),
        sa.Column('browser_hash',sa.String(64),nullable=False),
        sa.Column('config_hash',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('consumed',sa.Boolean,nullable=False),
        sa.Column('token_ciphertext',sa.Text,nullable=True),
        sa.Column('accounts',pg.JSONB,nullable=False),
        sa.Column('scopes',pg.JSONB,nullable=False),
        sa.Column('token_expires_at',sa.DateTime(timezone=True),nullable=True))
    op.create_table('instagram_connections',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('account_id',sa.String(100),nullable=False),
        sa.Column('username',sa.String(100),nullable=False),
        sa.Column('token_ciphertext',sa.Text,nullable=False),
        sa.Column('scopes',pg.JSONB,nullable=False),
        sa.Column('config_hash',sa.String(64),nullable=False),
        sa.Column('token_expires_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('connected_at',sa.DateTime(timezone=True),nullable=False))

    op.create_table('managed_connections',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('platform',sa.String(30),nullable=False),
        sa.Column('label',sa.String(100),nullable=False),
        sa.Column('secret_ciphertext',sa.Text,nullable=False),
        sa.Column('details',pg.JSONB,nullable=False),
        sa.Column('verified_at',sa.DateTime(timezone=True),nullable=False))
    op.add_column('publications',sa.Column('connection_id',pg.UUID(as_uuid=True),sa.ForeignKey('managed_connections.id'),nullable=True))
    op.create_table('platform_app_settings',sa.Column('platform',sa.String(30),primary_key=True),sa.Column('ciphertext',sa.Text,nullable=False))

def downgrade():
    op.drop_table('platform_app_settings')
    op.drop_column('publications','connection_id')
    op.drop_table('managed_connections')
    op.drop_table('instagram_connections')
    op.drop_table('instagram_oauth_flows')
