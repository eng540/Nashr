"""Persist Meta client business identity and explicit connection check facts."""
from alembic import op
import sqlalchemy as sa
revision='0065_instagram_connection_facts'
down_revision='0064_instagram_execution_core'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('instagram_oauth_flows',sa.Column('client_business_id',sa.String(100),nullable=True))
    op.add_column('instagram_connections',sa.Column('client_business_id',sa.String(100),nullable=True))
    op.add_column('instagram_connections',sa.Column('token_type',sa.String(60),nullable=True))
    op.add_column('instagram_connections',sa.Column('enabled',sa.Boolean,nullable=False,server_default=sa.true()))
    op.add_column('instagram_connections',sa.Column('last_check_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('instagram_connections',sa.Column('last_check_ok',sa.Boolean,nullable=True))
    op.add_column('instagram_connections',sa.Column('last_check_error',sa.String(100),nullable=True))

def downgrade():
    for name in ['last_check_error','last_check_ok','last_check_at','enabled','token_type','client_business_id']:op.drop_column('instagram_connections',name)
    op.drop_column('instagram_oauth_flows','client_business_id')
