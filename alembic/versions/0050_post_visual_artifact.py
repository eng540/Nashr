"""Allow one approved visual Artifact to travel with an existing Post."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0050_post_visual_artifact"
down_revision: Union[str, Sequence[str], None] = "0049_seed_design_card_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("visual_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_posts_visual_artifact_id_artifacts",
        "posts",
        "artifacts",
        ["visual_artifact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_posts_visual_artifact_id",
        "posts",
        ["visual_artifact_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_posts_visual_artifact_id", "posts", type_="unique")
    op.drop_constraint("fk_posts_visual_artifact_id_artifacts", "posts", type_="foreignkey")
    op.drop_column("posts", "visual_artifact_id")
