import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.main import app
from app.api.routes import _job_payload
from app.application.identity_control_plane import EditorialIdentityControlPlaneService
from app.infrastructure.database.models import ArtifactModel, DiscoveryJobModel, KnowledgeUnitModel, PostModel, ProductionClaimModel, ProductionJobItemModel, ProductionJobModel, SourceModel
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
        assert status_payload["resolved_context"]["schema_version"] == 5
        assert status_payload["resolved_context"]["output_contract"]["key"] == "TELEGRAM_POST"
        assert status_payload["resolved_context"]["output_contract"]["version"] == 1
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
        assert payload["resolved_context"]["schema_version"] == 5
        assert payload["resolved_context"]["output_contract"]["key"] == "TELEGRAM_POST"
        assert payload["resolved_context"]["identity"]["key"] == "API_TEST_EDITORIAL_IDENTITY"
        assert payload["resolved_context"]["identity"]["version"] == 1
        assert payload["resolved_context"]["identity"]["definition"]["voice"] == "Precise and respectful"


@pytest.mark.asyncio
async def test_create_production_job_api_pins_selected_product(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()

    async def noop(job_id):
        return None

    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/production-jobs", json={
            "source_id": str(source_id),
            "scope": "SOURCE",
            "product_key": "ARABIC_LITERATURE_BRIEF_TELEGRAM_POST",
        })
        assert response.status_code == 202, response.text
        context = response.json()["resolved_context"]
        assert context["schema_version"] == 6
        assert context["product"]["key"] == "ARABIC_LITERATURE_BRIEF_TELEGRAM_POST"
        assert context["product"]["version"] == 2
        assert context["recipe"]["key"] == "BOOK_TO_TELEGRAM_POST_BRIEF"
        assert context["output_contract"]["key"] == "TELEGRAM_POST"
        assert context["policy"]["key"] == "EDITORIAL_DEFAULT"


@pytest.mark.asyncio
async def test_production_job_api_exposes_running_and_reconciliation_counts(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()

    async def noop(job_id):
        return None

    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/production-jobs", json={"source_id": str(source_id), "scope": "SOURCE"})
        assert created.status_code == 202
        job_id = UUID(created.json()["job_id"])

        async with SessionFactory() as session:
            job = (await session.execute(
                select(ProductionJobModel).where(ProductionJobModel.id == job_id)
            )).scalar_one()
            items = (await session.execute(
                select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id).order_by(ProductionJobItemModel.position)
            )).scalars().all()
            job.status = "FAILED"
            # Deliberately leave cached counters stale; API counts must reflect item rows.
            items[0].status = "RUNNING"
            items[1].status = "FAILED"
            items[1].error_code = "PROVIDER_OUTCOME_UNKNOWN"
            items[1].error_message = "Reconcile before retrying."
            await session.commit()

        response = await client.get(f"/production-jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["completed_items"] == 0
        assert payload["failed_items"] == 1
        assert payload["pending_items"] == 0
        assert payload["running_items"] == 1
        assert payload["reconciliation_required_items"] == 1
        assert payload["progress_percent"] == 50
        assert payload["next_action"] == "INSPECT_FAILURE"


@pytest.mark.asyncio
async def test_production_job_items_api_exposes_provider_reconciliation_fields():
    source_id, _ = await _api_fixture()
    async def noop(job_id):
        return None
    # Create a durable job through the API so the response uses the production serializer.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/production-jobs", json={"source_id": str(source_id), "scope": "SOURCE"})
        assert created.status_code == 202
        job_id = UUID(created.json()["job_id"])
        async with SessionFactory() as session:
            item = (await session.execute(
                select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job_id).order_by(ProductionJobItemModel.position)
            )).scalars().first()
            item.status = "FAILED"
            item.error_code = "PROVIDER_OUTCOME_UNKNOWN"
            item.provider_name = None
            item.provider_operation_status = None
            item.provider_operation_name = None
            await session.commit()
        response = await client.get(f"/production-jobs/{job_id}/items")
        assert response.status_code == 200
        item_payload = response.json()["items"][0]
        assert item_payload["error_code"] == "PROVIDER_OUTCOME_UNKNOWN"
        assert item_payload["provider_name"] is None
        assert item_payload["provider_operation_name"] is None
        assert "provider_operation_status" in item_payload
    monkeypatch.undo()



@pytest.mark.asyncio
async def test_production_claim_idempotency_replays_same_job(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()

    async def noop(job_id):
        return None

    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    payload = {
        "source_id": str(source_id),
        "scope": "SOURCE",
        "idempotency_key": "same-request-key",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/production-jobs", json=payload)
        replay = await client.post("/production-jobs", json=payload)
        assert first.status_code == 202
        assert replay.status_code == 202
        assert replay.json()["job_id"] == first.json()["job_id"]
        assert replay.json()["claim_id"] == first.json()["claim_id"]
        assert replay.json()["claim_id"] != replay.json()["job_id"]

    async with SessionFactory() as session:
        claim = (await session.execute(
            select(ProductionClaimModel).options(selectinload(ProductionClaimModel.job)).where(ProductionClaimModel.id == UUID(first.json()["claim_id"]))
        )).scalar_one()
        job = (await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == UUID(first.json()["job_id"]))
        )).scalar_one()
        assert job.claim_id == claim.id
        assert claim.job is not None and claim.job.id == job.id
        assert claim.id != job.id
        assert claim.idempotency_key == "same-request-key"
        assert len(claim.request_fingerprint) == 64
        assert claim.request_payload["source_id"] == str(source_id)


@pytest.mark.asyncio
async def test_production_claim_idempotency_rejects_key_reuse_for_different_request(monkeypatch: pytest.MonkeyPatch):
    source_id, unit_ids = await _api_fixture()

    async def noop(job_id):
        return None

    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/production-jobs", json={
            "source_id": str(source_id),
            "scope": "SOURCE",
            "idempotency_key": "reused-request-key",
        })
        conflict = await client.post("/production-jobs", json={
            "source_id": str(source_id),
            "scope": "SELECTION",
            "knowledge_unit_ids": [str(unit_ids[0])],
            "idempotency_key": "reused-request-key",
        })
        assert first.status_code == 202
        assert conflict.status_code == 400
        assert "different production request" in conflict.json()["detail"]



@pytest.mark.asyncio
async def test_same_settings_with_new_claim_key_creates_new_job(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()

    async def noop(job_id):
        return None

    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/production-jobs", json={
            "source_id": str(source_id),
            "scope": "SOURCE",
            "idempotency_key": "explicit-claim-one",
        })
        second = await client.post("/production-jobs", json={
            "source_id": str(source_id),
            "scope": "SOURCE",
            "idempotency_key": "explicit-claim-two",
        })
        assert first.status_code == 202
        assert second.status_code == 202
        assert second.json()["job_id"] != first.json()["job_id"]
        assert second.json()["claim_id"] != first.json()["claim_id"]
        assert first.json()["claim_id"] != first.json()["job_id"]
        assert second.json()["claim_id"] != second.json()["job_id"]



@pytest.mark.asyncio
async def test_same_idempotency_key_is_atomic_under_concurrent_submissions(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()

    async def noop(job_id):
        return None

    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "source_id": str(source_id),
            "scope": "SOURCE",
            "idempotency_key": "concurrent-same-claim",
        }
        first, second = await asyncio.gather(
            client.post("/production-jobs", json=payload),
            client.post("/production-jobs", json=payload),
        )
        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["job_id"] == second.json()["job_id"]
        assert first.json()["claim_id"] == second.json()["claim_id"]


@pytest.mark.asyncio
async def test_source_production_state_ignores_legacy_and_other_product_posts():
    source_id, unit_ids = await _api_fixture()
    async with SessionFactory() as session:
        selected_job_id = uuid4()
        other_job_id = uuid4()
        session.add_all([
            ProductionJobModel(
                id=selected_job_id, source_id=source_id, scope="SOURCE", status="COMPLETED",
                total_items=1, resolved_context={
                    "product": {"key": "LINE_A", "version": 1},
                    "identity": {"key": "IDENTITY_A", "version": 1},
                    "recipe": {"key": "RECIPE_A", "version": 2},
                },
            ),
            ProductionJobModel(
                id=other_job_id, source_id=source_id, scope="SOURCE", status="COMPLETED",
                total_items=1, resolved_context={
                    "product": {"key": "LINE_B", "version": 1},
                    "identity": {"key": "IDENTITY_A", "version": 1},
                    "recipe": {"key": "RECIPE_A", "version": 2},
                },
            ),
        ])
        await session.commit()
        session.add_all([
            PostModel(id=uuid4(), knowledge_unit_id=unit_ids[0], production_job_id=selected_job_id, content="Line A post", status="DRAFT"),
            PostModel(id=uuid4(), knowledge_unit_id=unit_ids[1], production_job_id=other_job_id, content="Line B post", status="DRAFT"),
            PostModel(id=uuid4(), knowledge_unit_id=unit_ids[1], content="Legacy post without provenance", status="DRAFT"),
        ])
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        matching = await client.get(
            "/sources",
            params={
                "product_key": "LINE_A", "product_version": 1,
                "identity_key": "IDENTITY_A", "identity_version": 1,
                "recipe_key": "RECIPE_A", "recipe_version": 2,
            },
        )
        assert matching.status_code == 200
        source = next(item for item in matching.json() if item["id"] == str(source_id))
        assert source["material_count"] == 2
        assert source["produced_count"] == 1
        assert source["pending_count"] == 1

        other_identity = await client.get(
            "/sources",
            params={
                "product_key": "LINE_A", "product_version": 1,
                "identity_key": "IDENTITY_B", "identity_version": 1,
                "recipe_key": "RECIPE_A", "recipe_version": 2,
            },
        )
        assert other_identity.status_code == 200
        source = next(item for item in other_identity.json() if item["id"] == str(source_id))
        assert source["produced_count"] == 0
        assert source["pending_count"] == 2


@pytest.mark.asyncio
async def test_legacy_job_without_claim_remains_readable_and_resumable(monkeypatch: pytest.MonkeyPatch):
    source_id, _ = await _api_fixture()
    legacy_job_id = uuid4()
    async with SessionFactory() as session:
        legacy_job = ProductionJobModel(
            id=legacy_job_id,
            source_id=source_id,
            scope="SOURCE",
            status="FAILED",
            total_items=0,
        )
        session.add(legacy_job)
        await session.commit()
        persisted = (await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == legacy_job_id)
        )).scalar_one()
        assert persisted.claim_id is None
        assert (await session.execute(
            select(ProductionClaimModel).where(ProductionClaimModel.source_id == source_id)
        )).scalars().all() == []

    async def noop(job_id):
        return None

    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/production-jobs/{legacy_job_id}")
        resumed = await client.post(
            f"/production-jobs/{legacy_job_id}/resume",
            json={"retry_failed": False},
        )
    assert response.status_code == 200
    assert response.json()["job_id"] == str(legacy_job_id)
    assert response.json()["claim_id"] is None
    assert resumed.status_code == 202
    assert resumed.json()["job_id"] == str(legacy_job_id)
    assert resumed.json()["claim_id"] is None
    assert resumed.json()["status"] == "QUEUED"


@pytest.mark.asyncio
async def test_book_map_returns_source_materials_without_topic_assignment():
    source_id = uuid4()
    material_id = uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename="legacy-book.pdf", mime_type="application/pdf",
            storage_path="./storage/test/legacy-book.pdf", size_bytes=10, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=material_id, source_id=source_id, topic_id=None, position=1,
            title="Unassigned material", content="Legacy content",
        ))
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/sources/{source_id}/book-map")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["count"] == 1
    assert payload["topics"] == []
    assert len(payload["materials"]) == 1
    assert payload["materials"][0]["id"] == str(material_id)
    assert payload["materials"][0]["topic_id"] is None



def test_discovery_job_payload_does_not_require_production_claim_fields():
    job = DiscoveryJobModel(
        id=uuid4(),
        source_id=uuid4(),
        status="RUNNING",
        stage="DISCOVERING",
        topics_total=3,
        topics_completed=1,
        chunks_total=4,
        chunks_completed=2,
        materials_discovered=5,
    )

    payload = _job_payload(job)

    assert payload["job_id"] == str(job.id)
    assert payload["source_id"] == str(job.source_id)
    assert payload["status"] == "RUNNING"
    assert payload["topics_completed"] == 1
    assert "claim_id" not in payload


@pytest.mark.asyncio
async def test_custom_direct_text_api_creates_a_tracked_job(monkeypatch: pytest.MonkeyPatch):
    async def noop(job_id):
        return None
    monkeypatch.setattr("app.api.routes.run_production_job", noop)
    body = {
        "scope": "SELECTION",
        "production_mode": "CUSTOM",
        "input_text": "Direct text for API integration test.",
        "custom_instructions": "Keep the result concise.",
        "recipe_key": "BOOK_TO_TELEGRAM_POST",
        "idempotency_key": f"custom-text-{uuid4()}",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/production-jobs", json=body)
        assert response.status_code == 202, response.text
        payload = response.json()
        status_response = await client.get(f"/production-jobs/{payload['job_id']}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert "request_details" in status_payload, status_response.text
        details = status_payload["request_details"]
        assert details["production_mode"] == "CUSTOM"
        assert details["custom_instructions"] == body["custom_instructions"]
        assert details["input_text_preview"] == body["input_text"]
        assert details["materials"][0]["title"] == body["input_text"]
        replay = await client.post("/production-jobs", json=body)
        assert replay.status_code == 202
        assert replay.json()["job_id"] == payload["job_id"]
        conflict = {**body, "custom_instructions": "A different request."}
        conflict_response = await client.post("/production-jobs", json=conflict)
        assert conflict_response.status_code == 400

    async with SessionFactory() as session:
        job = (await session.execute(
            select(ProductionJobModel).where(ProductionJobModel.id == UUID(payload["job_id"]))
        )).scalar_one()
        item = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.job_id == job.id)
        )).scalar_one()
        unit = (await session.execute(
            select(KnowledgeUnitModel).where(KnowledgeUnitModel.id == item.knowledge_unit_id)
        )).scalar_one()
        source = (await session.execute(
            select(SourceModel).where(SourceModel.id == unit.source_id)
        )).scalar_one()
        claim = (await session.execute(
            select(ProductionClaimModel).where(ProductionClaimModel.id == job.claim_id)
        )).scalar_one()
        assert unit.content == body["input_text"]
        assert source.mime_type == "application/vnd.nashr.inline-text"
        assert claim.request_payload["custom_instructions"] == body["custom_instructions"]
        assert claim.request_payload["product_key"] is None
