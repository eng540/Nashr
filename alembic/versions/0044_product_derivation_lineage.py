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
    op.add_column(
        "production_products",
        sa.Column(
            "parent_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("production_products.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "production_products",
        sa.Column(
            "derived_from_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("production_product_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_production_products_parent_product_id", "production_products", ["parent_product_id"])
    op.create_index("ix_production_products_derived_from_version_id", "production_products", ["derived_from_version_id"])


def downgrade() -> None:
    op.drop_index("ix_production_products_derived_from_version_id", table_name="production_products")
    op.drop_index("ix_production_products_parent_product_id", table_name="production_products")
    op.drop_column("production_products", "derived_from_version_id")
    op.drop_column("production_products", "parent_product_id")
