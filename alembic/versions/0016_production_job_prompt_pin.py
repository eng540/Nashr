"""Pin editorial prompt snapshot to each production job."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_production_job_prompt_pin"
down_revision: Union[str, Sequence[str], None] = "0015_control_plane_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("production_jobs", sa.Column("editorial_prompt_key", sa.String(length=200), nullable=True))
    op.add_column("production_jobs", sa.Column("editorial_prompt_version", sa.Integer(), nullable=True))
    op.add_column("production_jobs", sa.Column("editorial_prompt_body", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("production_jobs", "editorial_prompt_body")
    op.drop_column("production_jobs", "editorial_prompt_version")
    op.drop_column("production_jobs", "editorial_prompt_key")
