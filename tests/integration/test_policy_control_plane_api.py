import httpx
import pytest

from app.main import app


def policy_definition(max_chars: int = 10000) -> dict[str, object]:
    return {
        "min_content_chars": 10, "max_content_chars": max_chars,
        "required_terms": ["المصدر"], "forbidden_terms": ["مفبرك"], "allow_urls": False,
    }


@pytest.mark.asyncio
async def test_policy_lifecycle_versions_and_published_immutability():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        key = "TEST_EDITORIAL_POLICY"
        created = await client.post("/api/control/policies", json={
            "key": key, "name": "Editorial guardrails", "purpose": "Define declarative content validation rules.",
            "definition": policy_definition(),
        })
        assert created.status_code == 201, created.text
        assert created.json()["created_version"]["version"] == 1
        assert created.json()["created_version"]["status"] == "DRAFT"

        published_v1 = await client.post(f"/api/control/policies/{key}/versions/1/publish")
        assert published_v1.status_code == 200, published_v1.text
        draft_v2 = await client.post(f"/api/control/policies/{key}/versions", json={"definition": policy_definition(8000)})
        assert draft_v2.status_code == 201, draft_v2.text
        assert draft_v2.json()["version"] == 2
        immutable = await client.patch(f"/api/control/policies/{key}/versions/1", json={"definition": policy_definition(5000)})
        assert immutable.status_code == 409
        published_v2 = await client.post(f"/api/control/policies/{key}/versions/2/publish")
        assert published_v2.status_code == 200, published_v2.text
        detail = await client.get(f"/api/control/policies/{key}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["active_version"] == 2
        versions = {item["version"]: item for item in payload["versions"]}
        assert versions[1]["status"] == "ARCHIVED"
        assert versions[2]["status"] == "PUBLISHED"
        assert versions[2]["definition"]["allow_urls"] is False


@pytest.mark.asyncio
async def test_policy_rejects_invalid_ranges_conflicting_terms_and_unknown_fields():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        invalid_range = await client.post("/api/control/policies", json={
            "key": "TEST_POLICY_INVALID_RANGE", "name": "Invalid range",
            "purpose": "Minimum cannot exceed maximum.",
            "definition": {"min_content_chars": 50, "max_content_chars": 10, "required_terms": [], "forbidden_terms": [], "allow_urls": True},
        })
        assert invalid_range.status_code == 409
        conflicting = await client.post("/api/control/policies", json={
            "key": "TEST_POLICY_CONFLICT", "name": "Conflicting terms",
            "purpose": "A term cannot be both required and forbidden.",
            "definition": {**policy_definition(), "required_terms": ["نشر"], "forbidden_terms": ["نشر"]},
        })
        assert conflicting.status_code == 409
        unknown = await client.post("/api/control/policies", json={
            "key": "TEST_POLICY_UNKNOWN", "name": "Unknown field",
            "purpose": "Reject executable or provider-specific config.",
            "definition": {**policy_definition(), "python": "import os"},
        })
        assert unknown.status_code == 422
