from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.recipe_engine import ProduceVideoArtifactCapability, ProductionExecutionContext
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, ProductionJobItemModel, ProductionJobModel, SourceModel
from app.infrastructure.database.session import SessionFactory


class FakeVeoGenerator:
    provider_name = "google-veo"

    def __init__(self):
        self.start_calls = []
        self.poll_calls = []

    async def start(self, prompt, *, aspect_ratio, resolution, duration_seconds):
        self.start_calls.append((prompt, aspect_ratio, resolution, duration_seconds))
        return "operations/test-video-1"

    async def poll(self, operation_name):
        self.poll_calls.append(operation_name)
        if len(self.poll_calls) == 1:
            return type("Pending", (), {
                "operation_name": operation_name, "done": False, "status": "RUNNING",
                "content": None, "mime_type": None, "model": "fake-veo", "error_message": None,
            })()
        return type("Done", (), {
            "operation_name": operation_name, "done": True, "status": "SUCCEEDED",
            "content": b"fake-mp4-bytes", "mime_type": "video/mp4", "model": "fake-veo",
            "error_message": None,
        })()


class FakeVideoStorage:
    def __init__(self):
        self.put_calls = []
        self.deleted = []

    async def put(self, *, key, content, content_type):
        self.put_calls.append((key, content, content_type))
        return f"s3://nashr-media/{key}"

    async def delete(self, uri):
        self.deleted.append(uri)


async def _create_video_job_item():
    source_id, unit_id, job_id, item_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename="video-source.pdf", book_title="Video Source",
            mime_type="application/pdf", storage_path=f"./storage/test/{source_id}.pdf",
            size_bytes=10, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1,
            title="A journey at dawn", content="A source passage describing a journey through an old city at dawn.",
        ))
        session.add(ProductionJobModel(
            id=job_id, source_id=source_id, scope="SOURCE", status="RUNNING", total_items=1,
        ))
        session.add(ProductionJobItemModel(
            id=item_id, job_id=job_id, knowledge_unit_id=unit_id, position=1, status="RUNNING",
        ))
        await session.commit()
    return unit_id, job_id, item_id


@pytest.mark.asyncio
async def test_video_capability_persists_operation_and_reuses_it_until_artifact_is_saved():
    unit_id, job_id, item_id = await _create_video_job_item()
    contract = {
        "contract_id": str(uuid4()), "version_id": str(uuid4()), "key": "VIDEO_ARTIFACT", "version": 1,
        "definition": {
            "artifact_kind": "VIDEO", "mime_type": "video/mp4", "content_mode": "STORAGE_URI",
            "required_metadata_fields": ["title"], "max_content_chars": None,
        },
    }
    product = {
        "product_id": str(uuid4()), "version_id": str(uuid4()), "key": "ARABIC_LITERATURE_VIDEO", "version": 1,
        "definition": {
            "recipe_key": "BOOK_TO_VIDEO_ARTIFACT", "output_contract_key": "VIDEO_ARTIFACT",
            "policy_key": "EDITORIAL_DEFAULT", "audience": "Readers of Arabic literature",
            "experience": "A source-grounded vertical video",
        },
    }
    generator, storage = FakeVeoGenerator(), FakeVideoStorage()
    capability = ProduceVideoArtifactCapability(
        generator=generator, storage_factory=lambda: storage, poll_interval_seconds=0, timeout_seconds=5,
    )
    async with SessionFactory() as session:
        context = ProductionExecutionContext(
            session=session,
            inputs={
                "knowledge_unit_id": unit_id,
                "production_job_item_id": item_id,
                "provider_name": None,
                "provider_operation_name": None,
                "provider_operation_status": None,
            },
            configuration={},
            run_id=job_id,
            resolved_context={"output_contract": contract, "product": product},
            stage_configuration={
                "style_instructions": "Vertical editorial clip", "aspect_ratio": "9:16",
                "resolution": "720p", "duration_seconds": 5,
            },
        )
        artifact = await capability.execute(context)
        item = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.id == item_id)
        )).scalar_one()
        row = (await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == artifact.id)
        )).scalar_one()

    assert artifact.storage_uri.startswith("s3://nashr-media/artifacts/")
    assert artifact.kind == "VIDEO"
    assert artifact.mime_type == "video/mp4"
    assert artifact.metadata["duration_seconds"] == 5
    assert row.review_status == "DRAFT"
    assert item.provider_operation_name == "operations/test-video-1"
    assert item.provider_operation_status == "SUCCEEDED"
    assert len(generator.start_calls) == 1
    assert len(generator.poll_calls) == 2
    assert len(storage.put_calls) == 1
