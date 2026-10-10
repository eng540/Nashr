import httpx
import pytest

from app.main import app


def definition(recipe_key: str = "BOOK_TO_TELEGRAM_POST") -> dict[str, str]:
    return {
        "recipe_key": recipe_key,
        "output_contract_key": "TELEGRAM_POST",
        "policy_key": "EDITORIAL_DEFAULT",
        "audience": "Readers of Arabic literature",
        "experience": "Source-grounded content ready for review",
    }


@pytest.mark.asyncio
async def test_product_lifecycle_versions_and_published_reference_validation():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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
