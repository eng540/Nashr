"""Pin reviewed content and destination for new Telegram batch schedules only."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0056_telegram_batch_review'
down_revision='0055_distribution_selection'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('schedules',sa.Column('telegram_review',postgresql.JSONB(),nullable=True))

def downgrade():
    op.drop_column('schedules','telegram_review')
