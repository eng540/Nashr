"""Track source product and source version for independent derived products."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0044_product_derivation_lineage"
down_revision: Union[str, Sequence[str], None] = "0043_product_component_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The composite FK proves that the source version belongs to parent_product_id.
    op.create_unique_constraint(
        "uq_production_product_versions_id_product",
        "production_product_versions",
        ["id", "product_id"],
    )
    op.add_column(
        "production_products",
        sa.Column("parent_product_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "production_products",
        sa.Column("derived_from_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_production_products_parent_product_id",
        "production_products",
        "production_products",
        ["parent_product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_production_products_source_version_matches_parent",
        "production_products",
        "production_product_versions",
        ["derived_from_version_id", "parent_product_id"],
        ["id", "product_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_production_products_derivation_refs_pair",
        "production_products",
        "(parent_product_id IS NULL AND derived_from_version_id IS NULL) OR "
        "(parent_product_id IS NOT NULL AND derived_from_version_id IS NOT NULL)",
    )
    op.create_index("ix_production_products_parent_product_id", "production_products", ["parent_product_id"])
    op.create_index("ix_production_products_derived_from_version_id", "production_products", ["derived_from_version_id"])


def _guard_no_existing_lineage(connection) -> None:
    """Refuse rollback when it would erase persisted source relationships."""
    derived_count = connection.execute(
        sa.text(
            "SELECT count(*) FROM production_products "
            "WHERE parent_product_id IS NOT NULL OR derived_from_version_id IS NOT NULL"
        )
    ).scalar_one()
    if derived_count:
        raise RuntimeError(
            "Cannot downgrade 0044_product_derivation_lineage: derived products exist; "
            "export or explicitly remove lineage records before retrying."
        )


def downgrade() -> None:
    # Never silently erase lineage after real derived products have been created.
    _guard_no_existing_lineage(op.get_bind())

    op.drop_index("ix_production_products_derived_from_version_id", table_name="production_products")
    op.drop_index("ix_production_products_parent_product_id", table_name="production_products")
    op.drop_constraint("ck_production_products_derivation_refs_pair", "production_products", type_="check")
    op.drop_constraint("fk_production_products_source_version_matches_parent", "production_products", type_="foreignkey")
    op.drop_constraint("fk_production_products_parent_product_id", "production_products", type_="foreignkey")
    op.drop_column("production_products", "derived_from_version_id")
    op.drop_column("production_products", "parent_product_id")
    op.drop_constraint("uq_production_product_versions_id_product", "production_product_versions", type_="unique")
