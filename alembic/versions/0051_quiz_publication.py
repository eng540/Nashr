"""Add native quiz artifact references to publication and scheduling."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0051_quiz_publication"
down_revision: Union[str, Sequence[str], None] = "0050_post_visual_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_artifacts_kind", "artifacts", type_="check")
    op.create_check_constraint(
        "ck_artifacts_kind",
        "artifacts",
        "kind IN ('POST', 'TEXT', 'IMAGE', 'VIDEO', 'AUDIO', 'QUIZ')",
    )

    op.add_column(
        "publications",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_publications_artifact_id_artifacts",
        "publications",
        "artifacts",
        ["artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_publications_artifact_id", "publications", ["artifact_id"])

    op.alter_column("schedule_items", "post_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column(
        "schedule_items",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_schedule_items_artifact_id_artifacts",
        "schedule_items",
        "artifacts",
        ["artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_schedule_items_schedule_artifact",
        "schedule_items",
        ["schedule_id", "artifact_id"],
    )
    op.create_check_constraint(
        "ck_schedule_items_single_content_reference",
        "schedule_items",
        "((post_id IS NOT NULL AND artifact_id IS NULL) OR "
        "(post_id IS NULL AND artifact_id IS NOT NULL))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_schedule_items_single_content_reference", "schedule_items", type_="check")
    op.drop_constraint("uq_schedule_items_schedule_artifact", "schedule_items", type_="unique")
    op.drop_constraint("fk_schedule_items_artifact_id_artifacts", "schedule_items", type_="foreignkey")
    op.drop_column("schedule_items", "artifact_id")
    op.alter_column("schedule_items", "post_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    op.drop_index("ix_publications_artifact_id", table_name="publications")
    op.drop_constraint("fk_publications_artifact_id_artifacts", "publications", type_="foreignkey")
    op.drop_column("publications", "artifact_id")

    op.drop_constraint("ck_artifacts_kind", "artifacts", type_="check")
    op.create_check_constraint(
        "ck_artifacts_kind",
        "artifacts",
        "kind IN ('POST', 'TEXT', 'IMAGE', 'VIDEO', 'AUDIO')",
    )
