from uuid import uuid4

import pytest
from sqlalchemy import select

from app.adapters.audio_generation.gemini_tts import GeneratedAudio
from app.application.recipe_engine import ProduceAudioArtifactCapability, ProductionExecutionContext
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, ProductionJobModel, SourceModel
from app.infrastructure.database.session import SessionFactory


class FakeDrafter:
    async def draft(self, **kwargs):
        assert kwargs["system_prompt"]
        return "نص عربي قصير مناسب للإلقاء الصوتي."


class FakeAudioGenerator:
    def __init__(self):
        self.calls = []

    async def generate(self, text, *, voice, style):
        self.calls.append((text, voice, style))
        return GeneratedAudio(content=b"fake-wav-bytes", mime_type="audio/wav", model="fake-tts")


class FakeAudioStorage:
    def __init__(self):
        self.put_calls = []
        self.deleted = []

    async def put(self, *, key, content, content_type):
        self.put_calls.append((key, content, content_type))
        return f"s3://nashr-media/{key}"

    async def delete(self, uri):
        self.deleted.append(uri)


@pytest.mark.asyncio
async def test_audio_capability_persists_private_audio_artifact():
    source_id, unit_id, job_id = uuid4(), uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename="audio-source.pdf", book_title="Audio Source",
            mime_type="application/pdf", storage_path=f"./storage/test/{source_id}.pdf",
            size_bytes=10, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1,
            title="A literary passage", content="A source passage to narrate.",
        ))
        session.add(ProductionJobModel(
            id=job_id, source_id=source_id, scope="SOURCE", status="RUNNING", total_items=1,
        ))
        await session.commit()

    contract = {
        "contract_id": str(uuid4()), "version_id": str(uuid4()), "key": "AUDIO_ARTIFACT", "version": 1,
        "definition": {
            "artifact_kind": "AUDIO", "mime_type": "audio/wav", "content_mode": "STORAGE_URI",
            "required_metadata_fields": ["title"], "max_content_chars": None,
        },
    }
    product = {
        "product_id": str(uuid4()), "version_id": str(uuid4()), "key": "ARABIC_LITERATURE_AUDIO", "version": 1,
        "definition": {
            "recipe_key": "BOOK_TO_AUDIO_ARTIFACT", "output_contract_key": "AUDIO_ARTIFACT",
            "policy_key": "EDITORIAL_DEFAULT", "audience": "Readers and listeners",
            "experience": "A spoken literary narration",
        },
    }
    generator, storage = FakeAudioGenerator(), FakeAudioStorage()
    capability = ProduceAudioArtifactCapability(
        drafter=FakeDrafter(),
        audio_generator=generator,
        storage_factory=lambda: storage,
    )
    async with SessionFactory() as session:
        context = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id},
            configuration={"editorial_prompt": {"body": "Draft a source-grounded Arabic narration."}},
            run_id=job_id,
            resolved_context={"output_contract": contract, "product": product},
            stage_configuration={"style_instructions": "Clear Arabic narration", "voice": "Kore", "speech_style": "warm and measured"},
        )
        artifact = await capability.execute(context)
        row = (await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == artifact.id)
        )).scalar_one()

    assert artifact.kind == "AUDIO"
    assert artifact.content is None
    assert artifact.storage_uri.startswith("s3://nashr-media/artifacts/")
    assert artifact.mime_type == "audio/wav"
    assert artifact.metadata["transcript"] == "نص عربي قصير مناسب للإلقاء الصوتي."
    assert row.review_status == "DRAFT"
    assert generator.calls == [("نص عربي قصير مناسب للإلقاء الصوتي.", "Kore", "warm and measured")]
    assert len(storage.put_calls) == 1
