import httpx
import pytest

from app.main import app
from app.application.control_plane import ControlPlaneResolver
from app.infrastructure.database.session import SessionFactory


def definition(recipe_key: str = "BOOK_TO_TELEGRAM_POST") -> dict[str, str]:
    return {
        "recipe_key": recipe_key,
        "output_contract_key": "TELEGRAM_POST",
        "policy_key": "EDITORIAL_DEFAULT",
        "prompt_key": "TEST_PRODUCT_PROMPT",
        "identity_key": "TEST_PRODUCT_IDENTITY",
        "audience": "Readers of Arabic literature",
        "experience": "Source-grounded content ready for review",
    }


@pytest.mark.asyncio
async def test_product_lifecycle_versions_and_published_reference_validation():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        prompt = await client.post("/api/control/prompts", json={
            "key": "TEST_PRODUCT_PROMPT",
            "name": "Test Product Prompt",
            "purpose": "Version pinning fixture for product manifest tests.",
            "body": "Original test prompt version.",
        })
        assert prompt.status_code == 201, prompt.text
        assert prompt.json()["created_version"]["id"]
        prompt_detail = await client.get("/api/control/prompts/TEST_PRODUCT_PROMPT")
        assert prompt_detail.status_code == 200, prompt_detail.text
        assert prompt_detail.json()["versions"][0]["id"] == prompt.json()["created_version"]["id"]
        assert (await client.post("/api/control/prompts/TEST_PRODUCT_PROMPT/versions/1/publish")).status_code == 200

        identity = await client.post("/api/control/identities", json={
            "key": "TEST_PRODUCT_IDENTITY",
            "name": "Test Product Identity",
            "purpose": "Stable editorial identity for product manifest tests.",
            "definition": {
                "purpose": "Create source-grounded Arabic literary content.",
                "audience": "Readers of Arabic literature",
                "voice": "Careful literary editor",
                "tone": "Precise and restrained",
                "principles": ["Preserve source meaning"],
                "objectives": ["Faithful editorial output"],
                "constraints": ["Do not invent facts"],
            },
        })
        assert identity.status_code == 201, identity.text
        identity_publish = await client.post("/api/control/identities/TEST_PRODUCT_IDENTITY/versions/1/publish")
        assert identity_publish.status_code == 200, identity_publish.text

        seeded = await client.get("/api/control/products")
        assert seeded.status_code == 200, seeded.text
        keys = {item["key"] for item in seeded.json()}
        assert "ARABIC_LITERATURE_TELEGRAM_POST" in keys
        assert "ARABIC_LITERATURE_BRIEF_TELEGRAM_POST" in keys

        created = await client.post("/api/control/products", json={
            "key": "TEST_PRODUCT_LIFECYCLE",
            "name": "Test Product",
            "purpose": "Exercise the product control plane lifecycle.",
            "definition": definition(),
        })
        assert created.status_code == 201, created.text
        assert created.json()["created_version"]["status"] == "DRAFT"
        published_v1 = await client.post("/api/control/products/TEST_PRODUCT_LIFECYCLE/versions/1/publish")
        assert published_v1.status_code == 200, published_v1.text
        manifest_v1 = published_v1.json()["definition"]["component_versions"]
        assert set(manifest_v1) == {"prompt", "identity", "recipe", "policy", "output_contract"}
        assert manifest_v1["prompt"]["key"] == "TEST_PRODUCT_PROMPT"
        assert manifest_v1["prompt"]["version"] == 1
        assert manifest_v1["identity"]["key"] == "TEST_PRODUCT_IDENTITY"

        prompt_v2 = await client.post("/api/control/prompts/TEST_PRODUCT_PROMPT/versions", json={
            "body": "Updated prompt used only by newly published product versions.",
        })
        assert prompt_v2.status_code == 201, prompt_v2.text
        assert (await client.post("/api/control/prompts/TEST_PRODUCT_PROMPT/versions/2/publish")).status_code == 200
        async with SessionFactory() as session:
            pinned_prompt_v1 = await ControlPlaneResolver().resolve_prompt_version(session, manifest_v1["prompt"])
            assert pinned_prompt_v1.version == 1
            assert str(pinned_prompt_v1.version_id) == manifest_v1["prompt"]["version_id"]

        draft_v2 = await client.post("/api/control/products/TEST_PRODUCT_LIFECYCLE/versions", json={
            "definition": definition("BOOK_TO_TELEGRAM_POST_BRIEF"),
        })
        assert draft_v2.status_code == 201, draft_v2.text
        assert draft_v2.json()["version"] == 2
        published_v2 = await client.post("/api/control/products/TEST_PRODUCT_LIFECYCLE/versions/2/publish")
        assert published_v2.status_code == 200, published_v2.text

        detail = await client.get("/api/control/products/TEST_PRODUCT_LIFECYCLE")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["active_version"] == 2
        versions = {item["version"]: item for item in payload["versions"]}
        assert versions[1]["status"] == "ARCHIVED"
        assert versions[2]["status"] == "PUBLISHED"
        assert versions[2]["definition"]["recipe_key"] == "BOOK_TO_TELEGRAM_POST_BRIEF"
        assert versions[1]["definition"]["component_versions"]["prompt"] == manifest_v1["prompt"]
        assert versions[2]["definition"]["component_versions"]["prompt"]["version"] == 2
        assert versions[2]["definition"]["component_versions"]["recipe"]["key"] == "BOOK_TO_TELEGRAM_POST_BRIEF"
        assert versions[2]["definition"]["component_versions"]["recipe"]["version"] == 1

        # Source product v1 is ARCHIVED and its pinned prompt v1 is ARCHIVED too.
        # An untouched derived product must retain that exact historical component ref.
        archived_source = await client.get("/api/control/products/TEST_PRODUCT_LIFECYCLE")
        assert archived_source.status_code == 200
        archived_source_v1 = next(v for v in archived_source.json()["versions"] if v["version"] == 1)
        assert archived_source_v1["status"] == "ARCHIVED"
        assert archived_source_v1["definition"]["component_versions"]["prompt"] == manifest_v1["prompt"]

        unchanged_derived = await client.post(
            "/api/control/products/TEST_PRODUCT_LIFECYCLE/versions/1/derive",
            json={
                "key": "TEST_PRODUCT_DERIVED_ARCHIVED_REFS",
                "name": "Derived product preserving archived references",
                "purpose": "Prove unchanged archived component refs remain pinned",
            },
        )
        assert unchanged_derived.status_code == 201, unchanged_derived.text
        unchanged_published = await client.post(
            "/api/control/products/TEST_PRODUCT_DERIVED_ARCHIVED_REFS/versions/1/publish"
        )
        assert unchanged_published.status_code == 200, unchanged_published.text
        unchanged_manifest = unchanged_published.json()["definition"]["component_versions"]
        assert unchanged_manifest == manifest_v1
        assert unchanged_manifest["prompt"] == manifest_v1["prompt"]
        async with SessionFactory() as session:
            archived_prompt = await ControlPlaneResolver().resolve_prompt_version(session, unchanged_manifest["prompt"])
            assert archived_prompt.version == 1
            assert str(archived_prompt.version_id) == manifest_v1["prompt"]["version_id"]
        prompt_detail = await client.get("/api/control/prompts/TEST_PRODUCT_PROMPT")
        assert prompt_detail.status_code == 200, prompt_detail.text
        archived_prompt_v1 = next(v for v in prompt_detail.json()["versions"] if v["version"] == 1)
        assert archived_prompt_v1["status"] == "ARCHIVED"

        prompt_alt = await client.post("/api/control/prompts", json={
            "key": "TEST_PRODUCT_PROMPT_ALT",
            "name": "Alternate Product Prompt",
            "purpose": "Replacement instruction component for derivation tests.",
            "body": "Alternate product instructions.",
        })
        assert prompt_alt.status_code == 201, prompt_alt.text
        assert (await client.post("/api/control/prompts/TEST_PRODUCT_PROMPT_ALT/versions/1/publish")).status_code == 200

        derived = await client.post("/api/control/products/TEST_PRODUCT_LIFECYCLE/versions/1/derive", json={
            "key": "TEST_PRODUCT_DERIVED",
            "name": "Derived Product",
            "purpose": "Independent derived product fixture",
        })
        assert derived.status_code == 201, derived.text
        derived_payload = derived.json()
        assert derived_payload["parent_product_id"] is not None
        assert derived_payload["derived_from_version_id"] == published_v1.json()["id"]
        derived_definition = derived_payload["created_version"]["definition"]
        assert derived_definition["component_versions"] == manifest_v1

        derived_definition["audience"] = "Audience unique to the derived product"
        derived_definition["prompt_key"] = "TEST_PRODUCT_PROMPT_ALT"
        derived_definition["component_versions"].pop("prompt")
        derived_draft = await client.patch("/api/control/products/TEST_PRODUCT_DERIVED/versions/1", json={
            "definition": derived_definition,
        })
        assert derived_draft.status_code == 200, derived_draft.text
        derived_published = await client.post("/api/control/products/TEST_PRODUCT_DERIVED/versions/1/publish")
        assert derived_published.status_code == 200, derived_published.text
        derived_manifest = derived_published.json()["definition"]["component_versions"]
        assert derived_manifest["prompt"]["key"] == "TEST_PRODUCT_PROMPT_ALT"
        assert derived_manifest["prompt"]["version"] == 1
        for component in ("identity", "recipe", "policy", "output_contract"):
            assert derived_manifest[component] == manifest_v1[component]

        source_after_derivation = await client.get("/api/control/products/TEST_PRODUCT_LIFECYCLE")
        assert source_after_derivation.status_code == 200
        source_v1_after = next(v for v in source_after_derivation.json()["versions"] if v["version"] == 1)
        assert source_v1_after["definition"]["audience"] == "Readers of Arabic literature"
        assert source_v1_after["definition"]["component_versions"] == manifest_v1

        derived_detail = await client.get("/api/control/products/TEST_PRODUCT_DERIVED")
        assert derived_detail.status_code == 200
        derivation = derived_detail.json()["derivation"]
        assert derivation["parent_product_key"] == "TEST_PRODUCT_LIFECYCLE"
        assert derivation["source_version"] == 1
        assert derivation["changes"]["audience"]["from"] == "Readers of Arabic literature"
        assert derivation["changes"]["audience"]["to"] == "Audience unique to the derived product"
        assert derivation["changes"]["prompt_key"]["from"] == "TEST_PRODUCT_PROMPT"
        assert derivation["changes"]["prompt_key"]["to"] == "TEST_PRODUCT_PROMPT_ALT"
        assert derivation["component_diffs"]["prompt"]["from"]["key"] == "TEST_PRODUCT_PROMPT"
        assert derivation["component_diffs"]["prompt"]["to"]["key"] == "TEST_PRODUCT_PROMPT_ALT"


@pytest.mark.asyncio
async def test_product_cannot_publish_with_missing_component_reference():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/control/products", json={
            "key": "TEST_PRODUCT_MISSING_RECIPE",
            "name": "Invalid Product",
            "purpose": "Publication must validate all component references.",
            "definition": definition("MISSING_RECIPE"),
        })
        assert created.status_code == 201, created.text
        publish = await client.post("/api/control/products/TEST_PRODUCT_MISSING_RECIPE/versions/1/publish")
        assert publish.status_code == 404



@pytest.mark.asyncio
async def test_derivation_database_constraints_keep_source_version_with_its_parent():
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.infrastructure.database.models import ProductionProductModel

    async with SessionFactory() as session:
        source = (await session.execute(
            text("SELECT id FROM production_products WHERE key = 'ARABIC_LITERATURE_TELEGRAM_POST'")
        )).scalar_one()
        source_version = (await session.execute(
            text("SELECT id FROM production_product_versions WHERE product_id = :product_id ORDER BY version DESC LIMIT 1"),
            {"product_id": source},
        )).scalar_one()
        other = ProductionProductModel(key="TEST_DERIVATION_OTHER", name="Other", purpose="Constraint test")
        session.add(other)
        await session.flush()
        wrong_version = ProductionProductModel(
            key="TEST_DERIVATION_WRONG_SOURCE", name="Wrong source", purpose="Must be rejected",
            parent_product_id=other.id, derived_from_version_id=source_version,
        )
        session.add(wrong_version)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async with SessionFactory() as session:
        source = (await session.execute(
            text("SELECT id FROM production_products WHERE key = 'ARABIC_LITERATURE_TELEGRAM_POST'")
        )).scalar_one()
        invalid_half_reference = ProductionProductModel(
            key="TEST_DERIVATION_HALF_REF", name="Half ref", purpose="Must be rejected",
            parent_product_id=source, derived_from_version_id=None,
        )
        session.add(invalid_half_reference)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


def test_derivation_migration_downgrade_refuses_to_drop_existing_lineage(monkeypatch):
    import importlib.util
    from pathlib import Path

    migration_path = Path(__file__).parents[2] / "alembic" / "versions" / "0044_product_derivation_lineage.py"
    spec = importlib.util.spec_from_file_location("migration_0044_product_derivation_lineage_test", migration_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    class Result:
        def scalar_one(self):
            return 1

    class Connection:
        def execute(self, statement):
            assert "production_products" in str(statement)
            return Result()

    drops = []
    monkeypatch.setattr(migration.op, "get_bind", lambda: Connection())
    monkeypatch.setattr(migration.op, "drop_index", lambda *args, **kwargs: drops.append(("index", args)))
    with pytest.raises(RuntimeError, match="derived products exist"):
        migration.downgrade()
    assert drops == []



@pytest.mark.asyncio
async def test_downgrade_guard_blocks_rollback_when_real_derived_product_exists(monkeypatch):
    import importlib.util
    from pathlib import Path
    from uuid import uuid4

    migration_path = Path(__file__).parents[2] / "alembic" / "versions" / "0044_product_derivation_lineage.py"
    spec = importlib.util.spec_from_file_location("migration_0044_real_lineage_guard_test", migration_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        source_response = await client.get("/api/control/products/ARABIC_LITERATURE_TELEGRAM_POST")
        assert source_response.status_code == 200, source_response.text
        source = source_response.json()
        source_version = next(
            version for version in source["versions"] if version["version"] == source["active_version"]
        )
        derived_key = "TEST_ROLLBACK_GUARD_" + uuid4().hex.upper()
        created = await client.post(
            f"/api/control/products/ARABIC_LITERATURE_TELEGRAM_POST/versions/{source_version['version']}/derive",
            json={
                "key": derived_key,
                "name": "Rollback guard fixture",
                "purpose": "Prove a real lineage row blocks destructive downgrade",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["parent_product_id"] == source["id"]
        assert created.json()["derived_from_version_id"] == source_version["id"]

    async with SessionFactory() as session:
        connection = await session.connection()

        def attempt_downgrade(sync_connection):
            monkeypatch.setattr(migration.op, "get_bind", lambda: sync_connection)
            with pytest.raises(RuntimeError, match="derived products exist"):
                migration.downgrade()

        # Invoke the actual Alembic downgrade function against the real test DB
        # connection after creating a persisted derived product above.
        await connection.run_sync(attempt_downgrade)



def test_derivation_migration_downgrade_removes_constraints_when_no_lineage_exists(monkeypatch):
    import importlib.util
    from pathlib import Path

    migration_path = Path(__file__).parents[2] / "alembic" / "versions" / "0044_product_derivation_lineage.py"
    spec = importlib.util.spec_from_file_location("migration_0044_empty_lineage_downgrade_test", migration_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    class Result:
        def scalar_one(self):
            return 0

    class Connection:
        def execute(self, statement):
            assert "production_products" in str(statement)
            return Result()

    operations = []
    monkeypatch.setattr(migration.op, "get_bind", lambda: Connection())
    monkeypatch.setattr(migration.op, "drop_index", lambda *args, **kwargs: operations.append(("index", args[0])))
    monkeypatch.setattr(migration.op, "drop_constraint", lambda *args, **kwargs: operations.append(("constraint", args[0])))
    monkeypatch.setattr(migration.op, "drop_column", lambda *args, **kwargs: operations.append(("column", args[1])))

    migration.downgrade()

    assert operations == [
        ("index", "ix_production_products_derived_from_version_id"),
        ("index", "ix_production_products_parent_product_id"),
        ("constraint", "ck_production_products_derivation_refs_pair"),
        ("constraint", "fk_production_products_source_version_matches_parent"),
        ("constraint", "fk_production_products_parent_product_id"),
        ("column", "derived_from_version_id"),
        ("column", "parent_product_id"),
        ("constraint", "uq_production_product_versions_id_product"),
    ]
