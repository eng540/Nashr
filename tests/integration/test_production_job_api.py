from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel


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
async def test_create_production_job_api_rejects_empty_selection():
    source_id, _ = await _api_fixture()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/production-jobs",
            json={"source_id": str(source_id), "scope": "SELECTION", "knowledge_unit_ids": []},
        )
        assert response.status_code == 400
