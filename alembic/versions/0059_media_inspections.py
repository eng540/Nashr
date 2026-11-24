"""Versioned private inspection evidence, separate from execution."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0059_media_inspections'
down_revision='0058_platform_copy_media'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('platform_media_inspections',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id',ondelete='CASCADE'),nullable=False),
        sa.Column('platform',sa.String(30),nullable=False),
        sa.Column('source_fingerprint',sa.String(64),nullable=False),
        sa.Column('copy_version',sa.Integer,nullable=False),
        sa.Column('media_id',pg.UUID(as_uuid=True),sa.ForeignKey('platform_copy_media.id'),nullable=True),
        sa.Column('selected',sa.Boolean,nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('probe_version',sa.String(30),nullable=False),
        sa.Column('result',pg.JSONB,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index('ix_media_inspections_artifact_platform','platform_media_inspections',['artifact_id','platform'])

def downgrade():
    op.drop_index('ix_media_inspections_artifact_platform',table_name='platform_media_inspections')
    op.drop_table('platform_media_inspections')
