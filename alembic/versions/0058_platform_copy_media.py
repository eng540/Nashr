"""Private immutable media for individual platform copies, no schedule changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0058_platform_copy_media'
down_revision='0057_central_platform_copies'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('platform_copy_media',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('artifact_id',pg.UUID(as_uuid=True),sa.ForeignKey('artifacts.id',ondelete='CASCADE'),nullable=False),
        sa.Column('platform',sa.String(30),nullable=False),
        sa.Column('source_fingerprint',sa.String(64),nullable=False),
        sa.Column('source_sha256',sa.String(64),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('storage_uri',sa.Text,nullable=False),
        sa.Column('mime_type',sa.String(100),nullable=False),
        sa.Column('recipe',pg.JSONB,nullable=False),
        sa.Column('measurements',pg.JSONB,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index('ix_platform_copy_media_artifact_platform','platform_copy_media',['artifact_id','platform'])
    op.add_column('platform_copies',sa.Column('selected_media_id',pg.UUID(as_uuid=True),sa.ForeignKey('platform_copy_media.id'),nullable=True))

def downgrade():
    op.drop_column('platform_copies','selected_media_id')
    op.drop_index('ix_platform_copy_media_artifact_platform',table_name='platform_copy_media')
    op.drop_table('platform_copy_media')
