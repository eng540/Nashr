from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.recipe_engine import ProduceVideoArtifactCapability, ProductionExecutionContext
from app.application.control_plane import ControlPlaneResolver, PromptTemplateService
from app.application.identity_control_plane import EditorialIdentityControlPlaneService
from app.application.product_control_plane import ProductionProductControlPlaneService
from app.application.identity_context import compose_editorial_prompt
from app.domain.production_context import ResolvedProductionContext
from app.domain.products import ProductionProductDefinition
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, ProductionJobItemModel, ProductionJobModel, SourceModel
from app.infrastructure.database.session import SessionFactory


class FakeVeoGenerator:
    provider_name = "google-gemini-omni"

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
            "content": bytes([0, 0, 0, 16]) + b"ftypisom" + bytes([0, 0, 0, 0]), "mime_type": "video/mp4", "model": "fake-veo",
            "error_message": None,
        })()


class FakeVideoStorage:
    def __init__(self):
        self.ensure_available_calls = 0
        self.put_calls = []
        self.deleted = []

    async def ensure_available(self):
        self.ensure_available_calls += 1

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
async def test_video_capability_uses_the_published_products_pinned_prompt_and_identity(monkeypatch: pytest.MonkeyPatch):
    unit_id, job_id, item_id = await _create_video_job_item()
    publish_storage = FakeVideoStorage()
    monkeypatch.setattr(
        "app.application.product_control_plane.S3ArtifactStorage.from_environment",
        lambda *args, **kwargs: publish_storage,
    )
    product_key = "QUL_WA_LA_TAQUL_TEST_VIDEO_PRODUCT"
    prompt_key = "qul.wa_la_taqul.test"
    identity_key = "QUL_WA_LA_TAQUL_TEST_IDENTITY"
    prompt_body = (
        "QUL PRODUCT INSTRUCTION: state the common phrase, the corrected phrase, "
        "the reason, and one precise example. Do not claim grammatical certainty without evidence."
    )
    identity_definition = {
        "purpose": "تحرير تعليمي دقيق لقواعد الاستعمال اللغوي.",
        "audience": "متعّلمو العربية ومستخدموها.",
        "voice": "محرر لغوي عربي دقيق، يميز بين الشائع والصحيح دون تعالٍ.",
        "tone": "واضح، مقتصد، حازم عند ثبوت القاعدة ومتحفظ عند غياب الدليل.",
        "principles": ["بيّن الصواب مع السبب", "لا تختلق قاعدة"],
        "objectives": ["تعليم الاستعمال الصحيح"],
        "constraints": ["لا تجزم بلا دليل", "لا تسخر من الخطأ الشائع"],
    }

    async with SessionFactory() as session:
        prompts = PromptTemplateService(session)
        await prompts.create_template(
            prompt_key, "QUL test instructions", "Product-specific usage lesson instructions", prompt_body
        )
        await prompts.publish(prompt_key, 1)

        identities = EditorialIdentityControlPlaneService(session)
        await identities.create_identity(
            identity_key, "QUL test identity", "Editorial identity for the QUL product test", identity_definition
        )
        await identities.publish(identity_key, 1)

        products = ProductionProductControlPlaneService(session)
        await products.create_product(
            product_key,
            "QUL test video product",
            "A product-owned instruction and identity for language usage videos",
            {
                "recipe_key": "BOOK_TO_VIDEO_ARTIFACT",
                "output_contract_key": "VIDEO_ARTIFACT",
                "policy_key": "EDITORIAL_DEFAULT",
                "prompt_key": prompt_key,
                "identity_key": identity_key,
                "audience": "Arabic language learners",
                "experience": "A concise, evidence-based usage lesson ready for review",
            },
        )
        await products.publish(product_key, 1)

        resolver = ControlPlaneResolver()
        product = await resolver.resolve_product(session, product_key)
        definition = ProductionProductDefinition.from_dict(product.definition)
        assert definition.component_versions is not None
        refs = definition.component_versions
        pinned_prompt = await resolver.resolve_prompt_version(session, refs["prompt"])
        pinned_identity = await resolver.resolve_identity_version(session, refs["identity"])
        pinned_recipe = await resolver.resolve_recipe_version(session, refs["recipe"])
        pinned_contract = await resolver.resolve_output_contract_version(session, refs["output_contract"])
        pinned_policy = await resolver.resolve_policy_version(session, refs["policy"])
        resolved = ResolvedProductionContext.capture(
            pinned_prompt,
            recipe=pinned_recipe,
            identity=pinned_identity,
            output_contract=pinned_contract,
            policy=pinned_policy,
            product=product,
        )
        editorial_body = compose_editorial_prompt(pinned_prompt.body, pinned_identity)
        editorial_body += (
            f"\n\nProduct audience: {definition.audience}"
            f"\nProduct experience: {definition.experience}"
        )

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
            configuration={
                "editorial_prompt": {
                    "key": pinned_prompt.key,
                    "version": pinned_prompt.version,
                    "body": editorial_body,
                }
            },
            run_id=job_id,
            resolved_context=resolved.to_dict(),
            stage_configuration=pinned_recipe.stages[0].configuration,
        )
        artifact = await capability.execute(context)
        item = (await session.execute(
            select(ProductionJobItemModel).where(ProductionJobItemModel.id == item_id)
        )).scalar_one()
        row = (await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == artifact.id)
        )).scalar_one()

    manifest = resolved.product.definition["component_versions"]
    assert manifest["prompt"]["version_id"] == resolved.prompt_template.version_id
    assert manifest["identity"]["version_id"] == resolved.identity.version_id
    assert manifest["recipe"]["version_id"] == resolved.recipe.version_id
    assert manifest["output_contract"]["version_id"] == resolved.output_contract.version_id
    assert manifest["policy"]["version_id"] == resolved.policy.version_id
    assert artifact.storage_uri.startswith("s3://nashr-media/artifacts/")
    assert artifact.kind == "VIDEO"
    assert artifact.mime_type == "video/mp4"
    assert artifact.metadata["requested_duration_seconds"] == 5
    assert "QUL PRODUCT INSTRUCTION" in generator.start_calls[0][0]
    assert "state the common phrase" in generator.start_calls[0][0]
    assert identity_definition["voice"] in generator.start_calls[0][0]
    assert row.review_status == "DRAFT"
    assert item.provider_operation_name == "operations/test-video-1"
    assert item.provider_operation_status == "SUCCEEDED"
    assert len(generator.start_calls) == 1
    assert len(generator.poll_calls) == 2
    assert publish_storage.ensure_available_calls == 1
    assert storage.ensure_available_calls == 1
    assert len(storage.put_calls) == 1
