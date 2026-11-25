"""Read-only, bounded summaries for existing production jobs."""
from typing import Any, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import ProductionJobModel, SourceModel
from app.infrastructure.database.session import get_session

router = APIRouter()


@router.get("/production-jobs")
async def production_job_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    state: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"] | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    filters = [ProductionJobModel.status == state] if state else []
    total = (await session.execute(select(func.count()).select_from(ProductionJobModel).where(*filters))).scalar_one()
    rows = (await session.execute(
        select(ProductionJobModel.id, ProductionJobModel.source_id, SourceModel.filename,
               ProductionJobModel.scope, ProductionJobModel.status, ProductionJobModel.total_items,
               ProductionJobModel.completed_items, ProductionJobModel.failed_items,
               ProductionJobModel.created_at, ProductionJobModel.updated_at)
        .join(SourceModel, SourceModel.id == ProductionJobModel.source_id)
        .where(*filters).order_by(ProductionJobModel.created_at.desc(), ProductionJobModel.id.desc())
        .limit(limit).offset(offset)
    )).mappings().all()
    return {"items": [{"job_id": str(row["id"]), "source_id": str(row["source_id"]),
                       **{key: value for key, value in row.items() if key not in {"id", "source_id"}}}
                      for row in rows], "total": total, "limit": limit, "offset": offset}

