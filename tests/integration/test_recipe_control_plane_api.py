import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_recipe_control_plane_draft_publish_and_immutable_versions():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post(
            "/api/control/recipes",
            json={
                "key": "TEST_RECIPE_CONTROL_PLANE",
                "name": "Recipe Control Plane Test",
                "purpose": "Exercise recipe version lifecycle.",
                "stages": [
                    {
                        "key": "produce-post",
                        "capability_key": "produce_post",
                        "capability_version": 1,
                    }
                ],
            },
        )
        assert create.status_code == 201
        created = create.json()
        assert created["created_version"]["status"] == "DRAFT"
        assert created["created_version"]["version"] == 1

        publish_v1 = await client.post("/api/control/recipes/TEST_RECIPE_CONTROL_PLANE/versions/1/publish")
        assert publish_v1.status_code == 200
        assert publish_v1.json()["status"] == "PUBLISHED"

        create_v2 = await client.post(
            "/api/control/recipes/TEST_RECIPE_CONTROL_PLANE/versions",
            json={
                "stages": [
                    {
                        "key": "produce-post-v2",
                        "capability_key": "produce_post",
                        "capability_version": 1,
                    }
                ]
            },
        )
        assert create_v2.status_code == 201
        assert create_v2.json()["version"] == 2
        assert create_v2.json()["status"] == "DRAFT"

        update_published = await client.patch(
            "/api/control/recipes/TEST_RECIPE_CONTROL_PLANE/versions/1",
            json={
                "stages": [
                    {
                        "key": "changed",
                        "capability_key": "produce_post",
                        "capability_version": 1,
                    }
                ]
            },
        )
        assert update_published.status_code == 409

        publish_v2 = await client.post("/api/control/recipes/TEST_RECIPE_CONTROL_PLANE/versions/2/publish")
        assert publish_v2.status_code == 200
        assert publish_v2.json()["status"] == "PUBLISHED"

        detail = await client.get("/api/control/recipes/TEST_RECIPE_CONTROL_PLANE")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["active_version"] == 2
        versions = {row["version"]: row for row in payload["versions"]}
        assert versions[1]["status"] == "ARCHIVED"
        assert versions[2]["status"] == "PUBLISHED"
        assert versions[2]["stages"][0]["key"] == "produce-post-v2"

        invalid = await client.post(
            "/api/control/recipes/TEST_RECIPE_INVALID",
            json={
                "key": "TEST_RECIPE_INVALID",
                "name": "Invalid",
                "purpose": "Unknown capability must be rejected.",
                "stages": [
                    {
                        "key": "unknown",
                        "capability_key": "arbitrary_python",
                        "capability_version": 1,
                    }
                ],
            },
        )
        assert invalid.status_code == 409
