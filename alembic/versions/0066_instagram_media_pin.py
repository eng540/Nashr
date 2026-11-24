"""Bind dormant execution drafts to private inspection evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0066_instagram_media_pin'
down_revision='0065_instagram_connection_facts'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('instagram_executions', sa.Column('inspection_id', pg.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_instagram_execution_inspection', 'instagram_executions',
        'platform_media_inspections', ['inspection_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_instagram_execution_inspection', 'instagram_executions', type_='foreignkey')
    op.drop_column('instagram_executions', 'inspection_id')
