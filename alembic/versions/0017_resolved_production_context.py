"""Persist a versioned resolved-context snapshot for production jobs."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017_resolved_production_context"
down_revision: Union[str, Sequence[str], None] = "0016_production_job_prompt_pin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "production_jobs",
        sa.Column("resolved_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Backfill only when the historical key/version/body can be tied to an exact
    # persisted Control Plane version. Unknown provenance stays explicitly absent.
    op.execute(
        sa.text("""
            UPDATE production_jobs AS job
            SET resolved_context = jsonb_build_object(
                'schema_version', 1,
                'origin', 'LEGACY_PIN_BACKFILL',
                'captured_at', NULL,
                'prompt_template', jsonb_build_object(
                    'template_id', template.id::text,
                    'version_id', version.id::text,
                    'key', job.editorial_prompt_key,
                    'version', job.editorial_prompt_version,
                    'body', job.editorial_prompt_body
                )
            )
            FROM prompt_templates AS template
            JOIN prompt_template_versions AS version
              ON version.prompt_template_id = template.id
            WHERE template.key = job.editorial_prompt_key
              AND version.version = job.editorial_prompt_version
              AND version.body = job.editorial_prompt_body
              AND job.editorial_prompt_key IS NOT NULL
              AND job.editorial_prompt_version IS NOT NULL
              AND job.editorial_prompt_body IS NOT NULL
        """)
    )


def downgrade() -> None:
    op.drop_column("production_jobs", "resolved_context")
