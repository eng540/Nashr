"""Keep distribution intent outside approved content and media fingerprints."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0055_distribution_selection'
down_revision = '0054_live_location_operations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('distribution_selections',
        sa.Column('artifact_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('artifacts.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('platforms', postgresql.JSONB(), nullable=False),
        sa.Column('source_fingerprint', sa.String(64), nullable=False),
        sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table('distribution_selections')
