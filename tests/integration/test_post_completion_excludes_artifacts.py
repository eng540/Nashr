from uuid import uuid4

import httpx
import pytest

from app.main import app
from app.infrastructure.database.models import (
    ArtifactModel,
    KnowledgeUnitModel,
    ProductionJobModel,
    SourceModel,
)
from app.infrastructure.database.session import SessionFactory


@pytest.mark.asyncio
async def test_non_post_artifact_does_not_satisfy_post_completion_indicator():
    source_id, unit_id, job_id = uuid4(), uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id,
            filename="artifact-only.pdf",
            mime_type="application/pdf",
            storage_path="./storage/test/artifact-only.pdf",
            size_bytes=1,
            status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id,
            source_id=source_id,
            position=1,
            title="Artifact-only material",
            content="This material has an audio artifact but no text Post.",
        ))
        session.add(ProductionJobModel(
            id=job_id,
            source_id=source_id,
            scope="SOURCE",
            status="COMPLETED",
            total_items=1,
            resolved_context={
                "product": {"key": "LINE_ARTIFACT", "version": 1},
                "identity": None,
                "recipe": {"key": "RECIPE_AUDIO", "version": 1},
            },
        ))
        await session.commit()
        session.add(ArtifactModel(
            id=uuid4(),
            source_knowledge_unit_id=unit_id,
            kind="AUDIO",
            status="AVAILABLE",
            production_job_id=job_id,
            resolved_context={
                "product": {"key": "LINE_ARTIFACT", "version": 1},
                "identity": None,
                "recipe": {"key": "RECIPE_AUDIO", "version": 1},
            },
            storage_uri="s3://test/audio-only.mp3",
            mime_type="audio/mpeg",
        ))
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sources", params={
            "product_key": "LINE_ARTIFACT",
            "product_version": 1,
            "recipe_key": "RECIPE_AUDIO",
            "recipe_version": 1,
        })

    assert response.status_code == 200
    source = next(item for item in response.json() if item["id"] == str(source_id))
    # This endpoint is explicitly a Post-completion indicator. An Audio Artifact
    # must not be silently counted as a completed text Post.
    assert source["material_count"] == 1
    assert source["produced_count"] == 0
    assert source["pending_count"] == 1
