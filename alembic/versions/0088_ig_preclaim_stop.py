"""Allow immutable terminal preclaim Stop links with no capability."""
from alembic import op
import sqlalchemy as sa
revision='0088_ig_preclaim_stop'
down_revision='0087_ig_production_reads'
branch_labels=None
depends_on=None

def upgrade():
    op.alter_column('instagram_production_fences','grant_id',nullable=True)

def downgrade():
    op.alter_column('instagram_production_fences','grant_id',nullable=False)
