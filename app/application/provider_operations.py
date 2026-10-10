"""Persist and validate provider operation handles for resumable long-running work."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ProductionJobItemModel


PROVIDER_OPERATION_STATUSES = frozenset({"SUBMITTED", "RUNNING", "SUCCEEDED", "FAILED"})
_TERMINAL = frozenset({"SUCCEEDED", "FAILED"})


def _payload(item: ProductionJobItemModel) -> dict[str, object]:
    return {
        "item_id": str(item.id),
        "provider_name": item.provider_name,
        "operation_name": item.provider_operation_name,
        "status": item.provider_operation_status,
        "updated_at": item.provider_operation_updated_at,
    }


async def record_provider_operation(
    session: AsyncSession,
    *,
    item_id: UUID,
    provider_name: str,
    operation_name: str,
) -> dict[str, object]:
    if not isinstance(provider_name, str) or not provider_name.strip() or len(provider_name) > 100:
        raise ValueError("Provider name must be a non-empty string up to 100 characters.")
    if not isinstance(operation_name, str) or not operation_name.strip() or len(operation_name) > 500:
        raise ValueError("Provider operation name must be a non-empty string up to 500 characters.")
    item = (
        await session.execute(
            select(ProductionJobItemModel)
            .where(ProductionJobItemModel.id == item_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if item is None:
        raise LookupError("Production job item not found.")
    if item.provider_operation_name is not None:
        same_operation = (
            item.provider_name == provider_name
            and item.provider_operation_name == operation_name
        )
        if same_operation:
            return _payload(item)
        if item.provider_operation_status != "FAILED":
            raise ValueError("A non-failed provider operation cannot be replaced.")
    now = datetime.now(timezone.utc)
    item.provider_name = provider_name.strip()
    item.provider_operation_name = operation_name.strip()
    item.provider_operation_status = "SUBMITTED"
    item.provider_operation_updated_at = now
    item.updated_at = now
    await session.commit()
    await session.refresh(item)
    return _payload(item)


async def update_provider_operation_status(
    session: AsyncSession,
    *,
    item_id: UUID,
    status: str,
) -> dict[str, object]:
    if status not in PROVIDER_OPERATION_STATUSES:
        raise ValueError("Provider operation status is unsupported.")
    item = (
        await session.execute(
            select(ProductionJobItemModel)
            .where(ProductionJobItemModel.id == item_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if item is None:
        raise LookupError("Production job item not found.")
    current = item.provider_operation_status
    if item.provider_operation_name is None or current is None:
        raise ValueError("Production item has no recorded provider operation.")
    if current in _TERMINAL and status != current:
        raise ValueError("A terminal provider operation status cannot transition.")
    allowed = {
        "SUBMITTED": {"SUBMITTED", "RUNNING", "SUCCEEDED", "FAILED"},
        "RUNNING": {"RUNNING", "SUCCEEDED", "FAILED"},
        "SUCCEEDED": {"SUCCEEDED"},
        "FAILED": {"FAILED"},
    }
    if status not in allowed[current]:
        raise ValueError(f"Invalid provider operation status transition: {current} -> {status}.")
    now = datetime.now(timezone.utc)
    item.provider_operation_status = status
    item.provider_operation_updated_at = now
    item.updated_at = now
    await session.commit()
    await session.refresh(item)
    return _payload(item)
