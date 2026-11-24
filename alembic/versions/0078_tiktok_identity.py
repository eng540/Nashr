"""Connection-only TikTok identity, isolated from publishing."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0078_tiktok_identity'
down_revision='0077_facebook_reel_jobs'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('tiktok_connections',sa.Column('id',sa.Integer(),primary_key=True),
        *[sa.Column(n,sa.String(size),nullable=False) for n,size in [('open_id',100),('display_name',500),('config_hash',64)]],
        sa.Column('token_ciphertext',sa.Text(),nullable=False),sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('scopes',pg.JSONB(),nullable=False),
        sa.Column('last_check_ok',sa.Boolean(),nullable=True),
        *[sa.Column(n,sa.DateTime(timezone=True),nullable=True) for n in ['token_expires_at','last_check_at']],
        sa.Column('connected_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('tiktok_oauth_flows',
        *[sa.Column(n,sa.String(64),primary_key=n=='id',nullable=False) for n in ['id','session_hash','browser_hash','config_hash']],
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('consumed',sa.Boolean(),nullable=False),sa.Column('token_ciphertext',sa.Text(),nullable=True),sa.Column('accounts',pg.JSONB(),nullable=False))

def downgrade():
    op.drop_table('tiktok_oauth_flows');op.drop_table('tiktok_connections')
