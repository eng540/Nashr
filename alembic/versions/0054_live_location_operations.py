"""Track explicitly reviewed live location updates and stops."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0054_live_location_operations'
down_revision = '0053_album_publication_ids'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('live_location_operations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('publication_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('publications.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_live_location_operations_publication_id', 'live_location_operations', ['publication_id'])


def downgrade():
    op.drop_table('live_location_operations')
