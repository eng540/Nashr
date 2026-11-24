"""Separate catalog labels from immutable publication content and fingerprints."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0062_content_organization'
down_revision='0061_connection_lifecycle'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('artifact_organization',sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id',ondelete='CASCADE'),primary_key=True),sa.Column('title',sa.String(500),nullable=False,server_default=''),sa.Column('series',sa.String(200),nullable=False,server_default=''),sa.Column('category',sa.String(200),nullable=False,server_default=''),sa.Column('version',sa.Integer,nullable=False,server_default='1'),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():op.drop_table('artifact_organization')
