from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.adapters.image_generation.gemini import GeneratedImage
from app.application.recipe_engine import ProduceImageArtifactCapability, ProductionExecutionContext
from app.domain.artifacts import ArtifactKind
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, PostModel, SourceModel
from app.infrastructure.database.session import SessionFactory


class FakeImageGenerator:
    def __init__(self):
        self.calls = []

    async def generate(self, prompt, *, aspect_ratio="1:1", image_size="1K"):
        self.calls.append((prompt, aspect_ratio, image_size))
        return GeneratedImage(content=b"fake-png-bytes", mime_type="image/png", model="fake-image-model")


class FakeArtifactStorage:
    def __init__(self):
        self.put_calls = []
        self.deleted = []

    async def put(self, *, key, content, content_type):
        self.put_calls.append((key, content, content_type))
        return f"s3://nashr-media/{key}"

    async def delete(self, uri):
        self.deleted.append(uri)


async def _create_source_material():
    source_id, unit_id = uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename="image-source.pdf", book_title="Test Book",
            mime_type="application/pdf", storage_path=f"./storage/test/{source_id}.pdf",
            size_bytes=10, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1,
            title="A literary scene", content="A source passage about a traveler crossing an ancient city at dawn.",
        ))
        await session.commit()
    return source_id, unit_id


@pytest.mark.asyncio
async def test_image_capability_persists_private_draft_and_reuses_it_on_retry():
    _, unit_id = await _create_source_material()
    job_id = uuid4()
    contract = {
        "contract_id": str(uuid4()),
        "version_id": str(uuid4()),
        "key": "IMAGE_ARTIFACT",
        "version": 1,
        "definition": {
            "artifact_kind": "IMAGE",
            "mime_type": "image/png",
            "content_mode": "STORAGE_URI",
            "required_metadata_fields": ["title"],
            "max_content_chars": None,
        },
    }
    product = {
        "product_id": str(uuid4()),
        "version_id": str(uuid4()),
        "key": "ARABIC_LITERATURE_IMAGE",
        "version": 1,
        "definition": {
            "recipe_key": "BOOK_TO_IMAGE_ARTIFACT",
            "output_contract_key": "IMAGE_ARTIFACT",
            "policy_key": "EDITORIAL_DEFAULT",
            "audience": "Readers of Arabic literature and culture",
            "experience": "A source-grounded editorial illustration",
        },
    }
    resolved_context = {"output_contract": contract, "product": product}
    generator, storage = FakeImageGenerator(), FakeArtifactStorage()
    capability = ProduceImageArtifactCapability(generator=generator, storage_factory=lambda: storage)

    async with SessionFactory() as session:
        context = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id},
            configuration={},
            run_id=job_id,
            resolved_context=resolved_context,
            stage_configuration={"style_instructions": "Editorial illustration", "aspect_ratio": "4:5", "image_size": "1K"},
        )
        artifact = await capability.execute(context)
        retried = await capability.execute(context)
        row = (await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == artifact.id)
        )).scalar_one()
        posts = (await session.execute(
            select(PostModel).where(PostModel.knowledge_unit_id == unit_id)
        )).scalars().all()

    assert artifact.id == retried.id
    assert artifact.kind == ArtifactKind.IMAGE
    assert artifact.content is None
    assert artifact.storage_uri.startswith("s3://nashr-media/artifacts/")
    assert artifact.mime_type == "image/png"
    assert artifact.metadata["title"] == "A literary scene"
    assert row.review_status == "DRAFT"
    assert row.output_contract_key == "IMAGE_ARTIFACT"
    assert row.output_contract_version == 1
    assert len(generator.calls) == 1
    assert len(storage.put_calls) == 1
    assert posts == []
