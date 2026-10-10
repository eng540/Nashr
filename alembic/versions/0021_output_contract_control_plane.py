"""Persist versioned, provider-neutral output contracts."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0021_output_contracts"
down_revision: Union[str, Sequence[str], None] = "0020_identity_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "output_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_output_contracts_key"),
    )
    op.create_table(
        "output_contract_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_output_contract_versions_positive_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_output_contract_versions_status"),
        sa.ForeignKeyConstraint(["contract_id"], ["output_contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "version", name="uq_output_contract_versions_contract_version"),
    )
    op.create_index("ix_output_contract_versions_contract_id", "output_contract_versions", ["contract_id"])
    op.create_index(
        "uq_output_contract_versions_published",
        "output_contract_versions",
        ["contract_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )
    definition = {
        "artifact_kind": "POST",
        "mime_type": "text/plain",
        "content_mode": "INLINE",
        "required_metadata_fields": [],
        "max_content_chars": 100000,
    }
    op.execute(sa.text("""
        INSERT INTO output_contracts (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000911',
            'TELEGRAM_POST',
            'Telegram Post',
            'Inline editorial post content accepted by the existing Post and Telegram publication flow.'
        )
    """))
    op.get_bind().execute(
        sa.text("""
            INSERT INTO output_contract_versions (id, contract_id, version, definition, status)
            VALUES (
                '00000000-0000-0000-0000-000000000912',
                '00000000-0000-0000-0000-000000000911',
                1,
                CAST(:definition AS JSONB),
                'PUBLISHED'
            )
        """),
        {"definition": json.dumps(definition)},
    )


def downgrade() -> None:
    op.drop_index("uq_output_contract_versions_published", table_name="output_contract_versions")
    op.drop_index("ix_output_contract_versions_contract_id", table_name="output_contract_versions")
    op.drop_table("output_contract_versions")
    op.drop_table("output_contracts")
