"""Separate Instagram Login lifecycle. Preserve Page and Unified state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0073_instagram_direct_login'
down_revision='0072_instagram_page_login'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_direct_connections',sa.Column('id',sa.Integer(),primary_key=True),
        *[sa.Column(n,sa.String(size),nullable=False) for n,size in [('account_id',100),('username',100),('config_hash',64)]],
        sa.Column('scopes',pg.JSONB(),nullable=False),sa.Column('token_ciphertext',sa.Text(),nullable=False),sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('last_check_ok',sa.Boolean(),nullable=True),
        sa.Column('token_expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('last_check_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('connected_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('instagram_direct_oauth_flows',
        *[sa.Column(n,sa.String(64),primary_key=n=='id',nullable=False) for n in ['id','session_hash','browser_hash','config_hash']],
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('consumed',sa.Boolean(),nullable=False),sa.Column('token_ciphertext',sa.Text(),nullable=True),sa.Column('accounts',pg.JSONB(),nullable=False))

def downgrade():
    op.drop_table('instagram_direct_oauth_flows');op.drop_table('instagram_direct_connections')
