from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.application.identity_control_plane import EditorialIdentityControlPlaneService
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import SessionFactory


async def _api_fixture():
    source_id = uuid4()
    async with __import__("app.infrastructure.database.session", fromlist=["SessionFactory"]).SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename="api.pdf", mime_type="application/pdf",
            storage_path="./storage/test/api.pdf", size_bytes=10, status="STORED",
        ))
        for position in range(1, 3):
            session.add(KnowledgeUnitModel(
                id=uuid4(), source_id=source_id, position=position,
                title=f"API Material {position}", content=f"Content {position}",
            ))
        await session.commit()
        units = (await session.execute(
            select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id).order_by(KnowledgeUnitModel.position)
        )).scalars().all()
        return source_id, [unit.id for unit in units]


@pytest.mark.asyncio
async def test_create_and_read_production_job_api(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()
    async def noop(job_id):
        return None
    monkeypatch.setattr("app.api.routes.run_production_job", noop)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/production-jobs",
            json={"source_id": str(source_id), "scope": "SOURCE"},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["status"] == "QUEUED"
        assert payload["total_items"] == 2
        assert payload["pending_items"] == 2

        status_response = await client.get(f"/production-jobs/{payload['job_id']}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["job_id"] == payload["job_id"]
        assert status_payload["scope"] == "SOURCE"
        assert status_payload["pending_items"] == 2
        assert status_payload["progress_percent"] == 0
        assert status_payload["resolved_prompt"]["available"] is True
        assert status_payload["resolved_prompt"]["key"]
        assert status_payload["resolved_prompt"]["version"] >= 1
        assert status_payload["resolved_context"]["available"] is True
        assert status_payload["resolved_context"]["schema_version"] == 2
        assert status_payload["resolved_context"]["recipe"]["key"] == "BOOK_TO_TELEGRAM_POST"
        assert status_payload["resolved_context"]["recipe"]["version"] == 1
        assert status_payload["resolved_context"]["recipe"]["recipe_id"]
        assert status_payload["resolved_context"]["recipe"]["version_id"]
        assert status_payload["resolved_context"]["recipe"]["stages"][0]["capability_key"] == "produce_post"
        assert status_payload["resolved_context"]["origin"] == "RUNTIME_RESOLUTION"
        assert status_payload["resolved_context"]["prompt_template"]["key"] == status_payload["resolved_prompt"]["key"]
        assert status_payload["resolved_context"]["prompt_template"]["version"] == status_payload["resolved_prompt"]["version"]
        assert status_payload["resolved_context"]["prompt_template"]["template_id"]
        assert status_payload["resolved_context"]["prompt_template"]["version_id"]
        assert status_payload["next_action"] == "WAIT"

        items_response = await client.get(f"/production-jobs/{payload['job_id']}/items")
        assert items_response.status_code == 200
        items_payload = items_response.json()
        assert items_payload["total"] == 2
        assert items_payload["items"][0]["title"] == "API Material 1"
        assert items_payload["items"][0]["source_id"] == str(source_id)
        assert items_payload["items"][0]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_artifact_detail_api_returns_durable_output_and_provenance():
    source_id, unit_ids = await _api_fixture()
    artifact_id = uuid4()
    async with SessionFactory() as session:
        session.add(ArtifactModel(
            id=artifact_id,
            source_knowledge_unit_id=unit_ids[0],
            kind="TEXT",
            status="AVAILABLE",
            content="Durable text artifact",
            mime_type="text/plain",
            artifact_metadata={"test": True},
        ))
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/artifacts/{artifact_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(artifact_id)
        assert payload["kind"] == "TEXT"
        assert payload["status"] == "AVAILABLE"
        assert payload["source_knowledge_unit_id"] == str(unit_ids[0])
        assert payload["content"] == "Durable text artifact"
        assert payload["metadata"] == {"test": True}

        missing = await client.get(f"/artifacts/{uuid4()}")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_create_production_job_api_rejects_empty_selection():
    source_id, _ = await _api_fixture()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/production-jobs",
            json={"source_id": str(source_id), "scope": "SELECTION", "knowledge_unit_ids": []},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_production_job_api_pins_selected_editorial_identity(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()
    async with SessionFactory() as session:
        identities = EditorialIdentityControlPlaneService(session)
        await identities.create_identity(
            "API_TEST_EDITORIAL_IDENTITY",
            "API Test Identity",
            "Verify identity is passed through the production API.",
            {
                "purpose": "Help readers understand literary source material",
                "audience": "Arabic literature readers",
                "voice": "Precise and respectful",
                "tone": "Warm",
                "principles": ["Stay faithful to source"],
                "objectives": ["Encourage close reading"],
                "constraints": ["Do not invent quotations"],
            },
        )
        await identities.publish("API_TEST_EDITORIAL_IDENTITY", 1)

    async def noop(job_id):
        return None
    monkeypatch.setattr("app.api.routes.run_production_job", noop)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/production-jobs",
            json={
                "source_id": str(source_id),
                "scope": "SOURCE",
                "identity_key": "API_TEST_EDITORIAL_IDENTITY",
            },
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["resolved_context"]["schema_version"] == 3
        assert payload["resolved_context"]["identity"]["key"] == "API_TEST_EDITORIAL_IDENTITY"
        assert payload["resolved_context"]["identity"]["version"] == 1
        assert payload["resolved_context"]["identity"]["definition"]["voice"] == "Precise and respectful"
