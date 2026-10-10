import httpx
import pytest

from app.main import app


def contract_definition(
    artifact_kind: str = "TEXT",
    mime_type: str = "text/plain",
    content_mode: str = "INLINE",
    max_content_chars: int | None = 20000,
) -> dict[str, object]:
    return {
        "artifact_kind": artifact_kind,
        "mime_type": mime_type,
        "content_mode": content_mode,
        "required_metadata_fields": ["language"],
        "max_content_chars": max_content_chars,
    }


@pytest.mark.asyncio
async def test_output_contract_lifecycle_versions_and_published_immutability():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        key = "TEST_OUTPUT_CONTRACT"
        create = await client.post(
            "/api/control/output-contracts",
            json={
                "key": key,
                "name": "Test Text Contract",
                "purpose": "Validate versioned output contract lifecycle.",
                "definition": contract_definition(),
            },
        )
        assert create.status_code == 201, create.text
        assert create.json()["created_version"]["version"] == 1
        assert create.json()["created_version"]["status"] == "DRAFT"

        published_v1 = await client.post(f"/api/control/output-contracts/{key}/versions/1/publish")
        assert published_v1.status_code == 200, published_v1.text

        draft_v2 = await client.post(
            f"/api/control/output-contracts/{key}/versions",
            json={"definition": contract_definition(max_content_chars=10000)},
        )
        assert draft_v2.status_code == 201, draft_v2.text
        assert draft_v2.json()["version"] == 2

        mutate_published = await client.patch(
            f"/api/control/output-contracts/{key}/versions/1",
            json={"definition": contract_definition(max_content_chars=5000)},
        )
        assert mutate_published.status_code == 409

        published_v2 = await client.post(f"/api/control/output-contracts/{key}/versions/2/publish")
        assert published_v2.status_code == 200, published_v2.text
        detail = await client.get(f"/api/control/output-contracts/{key}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["active_version"] == 2
        versions = {item["version"]: item for item in payload["versions"]}
        assert versions[1]["status"] == "ARCHIVED"
        assert versions[2]["status"] == "PUBLISHED"
        assert versions[2]["definition"]["max_content_chars"] == 10000


@pytest.mark.asyncio
async def test_output_contract_rejects_kind_mime_mismatch_and_unknown_fields():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        invalid = await client.post(
            "/api/control/output-contracts",
            json={
                "key": "TEST_OUTPUT_CONTRACT_INVALID",
                "name": "Invalid Contract",
                "purpose": "MIME must match artifact kind.",
                "definition": contract_definition(
                    artifact_kind="IMAGE", mime_type="text/plain", content_mode="STORAGE_URI"
                ),
            },
        )
        assert invalid.status_code == 409

        unknown = await client.post(
            "/api/control/output-contracts",
            json={
                "key": "TEST_OUTPUT_CONTRACT_UNKNOWN",
                "name": "Unknown Field",
                "purpose": "Reject silently ignored fields.",
                "definition": {
                    **contract_definition(),
                    "provider": "provider-specific",
                },
            },
        )
        assert unknown.status_code == 422
