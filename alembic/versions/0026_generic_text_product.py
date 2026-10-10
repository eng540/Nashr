"""Seed the first generic TEXT production capability and product."""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0026_generic_text_product"
down_revision: Union[str, Sequence[str], None] = "0025_product_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    definition = {
        "artifact_kind": "TEXT",
        "mime_type": "text/plain",
        "content_mode": "INLINE",
        "required_metadata_fields": [],
        "max_content_chars": 100000,
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO output_contracts (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000951',
            'LITERARY_TEXT',
            'Literary Text',
            'Provider-neutral inline text output that is not an editorial Post.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO output_contract_versions (id, contract_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000952',
            '00000000-0000-0000-0000-000000000951',
            1,
            CAST(:definition AS JSONB),
            'PUBLISHED'
        )
    """), {"definition": json.dumps(definition)})

    op.get_bind().execute(sa.text("""
        INSERT INTO production_recipes (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000953',
            'BOOK_TO_TEXT',
            'Book to Text Artifact',
            'Produce a generic text Artifact from a selected book knowledge unit without creating a Post.'
        )
    """))
    recipe_definition = {
        "stages": [{
            "key": "produce-text",
            "capability_key": "produce_text",
            "capability_version": 1,
        }]
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO production_recipe_versions (id, recipe_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000954',
            '00000000-0000-0000-0000-000000000953',
            1,
            CAST(:definition AS JSONB),
            'PUBLISHED'
        )
    """), {"definition": json.dumps(recipe_definition, ensure_ascii=False)})

    product_definition = {
        "recipe_key": "BOOK_TO_TEXT",
        "output_contract_key": "LITERARY_TEXT",
        "policy_key": "EDITORIAL_DEFAULT",
        "audience": "Readers of Arabic literature and culture",
        "experience": "A source-grounded text artifact, separate from the editorial Post workflow",
    }
    op.get_bind().execute(sa.text("""
        INSERT INTO production_products (id, key, name, purpose)
        VALUES (
            '00000000-0000-0000-0000-000000000955',
            'ARABIC_LITERATURE_TEXT',
            'Arabic Literature Text',
            'Create a generic text artifact from Arabic literature source material.'
        )
    """))
    op.get_bind().execute(sa.text("""
        INSERT INTO production_product_versions (id, product_id, version, definition, status)
        VALUES (
            '00000000-0000-0000-0000-000000000956',
            '00000000-0000-0000-0000-000000000955',
            1,
            CAST(:definition AS JSONB),
            'PUBLISHED'
        )
    """), {"definition": json.dumps(product_definition, ensure_ascii=False)})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM production_product_versions WHERE id = '00000000-0000-0000-0000-000000000956'"))
    op.execute(sa.text("DELETE FROM production_products WHERE id = '00000000-0000-0000-0000-000000000955'"))
    op.execute(sa.text("DELETE FROM production_recipe_versions WHERE id = '00000000-0000-0000-0000-000000000954'"))
    op.execute(sa.text("DELETE FROM production_recipes WHERE id = '00000000-0000-0000-0000-000000000953'"))
    op.execute(sa.text("DELETE FROM output_contract_versions WHERE id = '00000000-0000-0000-0000-000000000952'"))
    op.execute(sa.text("DELETE FROM output_contracts WHERE id = '00000000-0000-0000-0000-000000000951'"))
