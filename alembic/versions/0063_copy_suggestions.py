"""Persist optional copy proposals separately from originals and publish copies."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0063_copy_suggestions'
down_revision='0062_content_organization'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('copy_suggestions',sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id',ondelete='CASCADE'),nullable=False),sa.Column('platform',sa.String(30),nullable=False),sa.Column('source_fingerprint',sa.String(64),nullable=False),sa.Column('copy_version',sa.Integer,nullable=False),sa.Column('fields_digest',sa.String(64),nullable=False),sa.Column('fields',pg.JSONB,nullable=False),sa.Column('prompt_version',sa.String(100),nullable=False),sa.Column('state',sa.String(30),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('applied_at',sa.DateTime(timezone=True),nullable=True))

def downgrade():op.drop_table('copy_suggestions')
