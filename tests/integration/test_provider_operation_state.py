from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.provider_operations import record_provider_operation, update_provider_operation_status
from app.infrastructure.database.models import KnowledgeUnitModel, ProductionJobItemModel, ProductionJobModel, SourceModel
from app.infrastructure.database.session import SessionFactory


async def _create_job_item():
    source_id, unit_id, job_id, item_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename="provider-operation.pdf", mime_type="application/pdf",
            storage_path=f"./storage/test/{source_id}.pdf", size_bytes=1, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1,
            title="Provider operation", content="Long-running generation source.",
        ))
        session.add(ProductionJobModel(
            id=job_id, source_id=source_id, scope="SOURCE", status="RUNNING", total_items=1,
        ))
        session.add(ProductionJobItemModel(
            id=item_id, job_id=job_id, knowledge_unit_id=unit_id, position=1, status="RUNNING",
        ))
        await session.commit()
    return item_id


@pytest.mark.asyncio
async def test_provider_operation_state_is_persisted_and_terminal_states_are_immutable():
    item_id = await _create_job_item()
    async with SessionFactory() as session:
        submitted = await record_provider_operation(
            session, item_id=item_id, provider_name="google-veo", operation_name="operations/123",
        )
        duplicate = await record_provider_operation(
            session, item_id=item_id, provider_name="google-veo", operation_name="operations/123",
        )
        running = await update_provider_operation_status(session, item_id=item_id, status="RUNNING")
        succeeded = await update_provider_operation_status(session, item_id=item_id, status="SUCCEEDED")
        with pytest.raises(ValueError, match="terminal"):
            await update_provider_operation_status(session, item_id=item_id, status="FAILED")
        with pytest.raises(ValueError, match="cannot be replaced"):
            await record_provider_operation(
                session, item_id=item_id, provider_name="google-veo", operation_name="operations/456",
            )
        row = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.id == item_id)
        )).scalar_one()

    assert submitted["status"] == "SUBMITTED"
    assert duplicate["operation_name"] == "operations/123"
    assert running["status"] == "RUNNING"
    assert succeeded["status"] == "SUCCEEDED"
    assert row.provider_name == "google-veo"
    assert row.provider_operation_name == "operations/123"
    assert row.provider_operation_status == "SUCCEEDED"
    assert row.provider_operation_updated_at is not None


@pytest.mark.asyncio
async def test_failed_provider_operation_can_be_replaced_on_retry():
    item_id = await _create_job_item()
    async with SessionFactory() as session:
        await record_provider_operation(
            session, item_id=item_id, provider_name="google-veo", operation_name="operations/old",
        )
        await update_provider_operation_status(session, item_id=item_id, status="FAILED")
        retried = await record_provider_operation(
            session, item_id=item_id, provider_name="google-veo", operation_name="operations/new",
        )

    assert retried["operation_name"] == "operations/new"
    assert retried["status"] == "SUBMITTED"
