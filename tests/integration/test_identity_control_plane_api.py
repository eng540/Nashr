import httpx
import pytest

from app.main import app


def definition(purpose: str = "Help readers discover enduring Arabic literature.") -> dict[str, object]:
    return {
        "purpose": purpose,
        "audience": "Arabic literature readers",
        "voice": "Rooted, clear, and respectful",
        "tone": "Warm and precise",
        "principles": ["Preserve source meaning", "Prefer primary text"],
        "objectives": ["Encourage close reading"],
        "constraints": ["Do not fabricate quotations"],
    }


@pytest.mark.asyncio
async def test_identity_control_plane_versions_are_managed_and_published_immutably():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        key = "TEST_IDENTITY_CONTROL_PLANE"
        created = await client.post(
            "/api/control/identities",
            json={
                "key": key,
                "name": "Arabic Literature",
                "purpose": "Editorial identity for literary content.",
                "definition": definition(),
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["created_version"]["status"] == "DRAFT"
        assert created.json()["created_version"]["version"] == 1

        published_v1 = await client.post(f"/api/control/identities/{key}/versions/1/publish")
        assert published_v1.status_code == 200, published_v1.text
        assert published_v1.json()["status"] == "PUBLISHED"

        draft_v2 = await client.post(
            f"/api/control/identities/{key}/versions",
            json={"definition": definition("Help readers explore Arabic literary heritage.")},
        )
        assert draft_v2.status_code == 201, draft_v2.text
        assert draft_v2.json()["version"] == 2
        assert draft_v2.json()["status"] == "DRAFT"

        mutate_published = await client.patch(
            f"/api/control/identities/{key}/versions/1",
            json={"definition": definition("Mutated published identity")},
        )
        assert mutate_published.status_code == 409

        published_v2 = await client.post(f"/api/control/identities/{key}/versions/2/publish")
        assert published_v2.status_code == 200, published_v2.text

        detail = await client.get(f"/api/control/identities/{key}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["active_version"] == 2
        versions = {item["version"]: item for item in payload["versions"]}
        assert versions[1]["status"] == "ARCHIVED"
        assert versions[2]["status"] == "PUBLISHED"
        assert versions[2]["definition"]["purpose"] == "Help readers explore Arabic literary heritage."


@pytest.mark.asyncio
async def test_identity_control_plane_rejects_invalid_definition_and_duplicate_key():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        key = "TEST_IDENTITY_INVALID"
        payload = {
            "key": key,
            "name": "Invalid test identity",
            "purpose": "Validation boundary test.",
            "definition": definition(),
        }
        first = await client.post("/api/control/identities", json=payload)
        assert first.status_code == 201, first.text
        duplicate = await client.post("/api/control/identities", json=payload)
        assert duplicate.status_code == 409

        invalid = {
            **payload,
            "key": "TEST_IDENTITY_INVALID_DEFINITION",
            "definition": {**definition(), "voice": "   "},
        }
        response = await client.post("/api/control/identities", json=invalid)
        assert response.status_code == 409
