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
