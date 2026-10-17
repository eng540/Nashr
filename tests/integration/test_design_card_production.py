import hashlib
from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID, uuid4

import pytest
import httpx
from PIL import Image
from sqlalchemy import select, text

from app.application.artifacts import persist_generic_artifact
from app.application.image_generation import GeneratedImage
from app.application.generic_artifact_review import GenericArtifactReviewService
from app.application.recipe_engine import ProductionExecutionContext, RenderApprovedTextCardCapability
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import ArtifactModel, KnowledgeUnitModel, PostModel, ProductionClaimModel, ProductionJobModel, SourceModel
from app.infrastructure.database.session import SessionFactory
from app.main import app


class MemoryCardStorage:
    def __init__(self):
        self.objects = {}

    async def ensure_available(self):
        return None

    async def put(self, *, key: str, content: bytes, content_type: str):
        assert content_type == "image/png"
        assert content.startswith(bytes.fromhex("89504e470d0a1a0a"))
        uri = f"s3://test/{key}"
        self.objects[uri] = content
        return uri

    async def delete(self, uri: str):
        self.objects.pop(uri, None)


def _pinned_contract(key: str, kind: str, mime_type: str, mode: str, required_fields: list[str]):
    return {
        "contract_id": str(uuid4()),
        "version_id": str(uuid4()),
        "key": key,
        "version": 1,
        "definition": {
            "artifact_kind": kind,
            "mime_type": mime_type,
            "content_mode": mode,
            "required_metadata_fields": required_fields,
            "max_content_chars": 10000 if mode == "INLINE" else None,
        },
    }


@pytest.mark.asyncio
async def test_approved_text_to_card_capability_persists_png_with_provenance():

    storage = MemoryCardStorage()
    source_id, unit_id, run_id = uuid4(), uuid4(), uuid4()
    text_contract = _pinned_contract("CARD_SOURCE_TEXT", "TEXT", "text/plain", "INLINE", ["language"])
    text_context = {"output_contract": text_contract}
    approved_text = "إِنَّ حفظَ النصِّ المعتمدِ أصلٌ لا يُعادُ توليدُه."

    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id,
            filename="arabic-book.pdf",
            mime_type="application/pdf",
            storage_path=f"./storage/test/{source_id}.pdf",
            size_bytes=10,
            status="STORED",
            book_title="كتاب الأمثلة",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id,
            source_id=source_id,
            position=1,
            title="حفظ النص",
            content="مادة المصدر",
            source_reference="ص. 11",
        ))
        await session.flush()
        claim_id = uuid4()
        claim = ProductionClaimModel(
            id=claim_id,
            source_id=source_id,
            scope="SELECTION",
            request_fingerprint="a" * 64,
            request_payload={"source_id": str(source_id)},
        )
        session.add(claim)
        await session.flush()
        session.add(ProductionJobModel(
            id=run_id,
            claim_id=claim_id,
            source_id=source_id,
            scope="SELECTION",
            status="RUNNING",
            total_items=1,
        ))
        await session.commit()

        now = datetime.now(timezone.utc)
        text_artifact = Artifact(
            id=uuid4(),
            source_knowledge_unit_id=unit_id,
            kind=ArtifactKind.TEXT,
            content=approved_text,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            mime_type="text/plain",
            output_contract_key="CARD_SOURCE_TEXT",
            output_contract_version=1,
            resolved_context=text_context,
            metadata={"title": "النص المعتمد", "language": "ar"},
        )
        saved_text = await persist_generic_artifact(session, text_artifact, resolved_context=text_context)
        await GenericArtifactReviewService(session).approve(saved_text.id, "Human-approved for card rendering")

        image_contract = _pinned_contract("CARD_IMAGE_PNG", "IMAGE", "image/png", "STORAGE_URI", ["source_artifact_id"])
        pinned_product = {"key": "ARABIC_LITERATURE_DESIGN_CARD", "version": 1, "version_id": str(uuid4())}
        pinned_recipe = {"key": "APPROVED_TEXT_TO_DESIGN_CARD", "version": 1, "version_id": str(uuid4())}
        image_resolved_context = {
            "product": pinned_product,
            "recipe": pinned_recipe,
            "output_contract": image_contract,
        }
        context = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id, "source_artifact_id": saved_text.id},
            configuration={},
            run_id=run_id,
            resolved_context=image_resolved_context,
            stage_configuration={
                "width": 640,
                "height": 800,
                "padding": 40,
                "font_size": 30,
                "line_spacing": 10,
                "max_lines": 20,
                "font_family": "naskh",
                "show_title": True,
                "show_source_attribution": True,
            },
        )
        image_artifact = await RenderApprovedTextCardCapability(
            storage_factory=lambda: storage
        ).execute(context)

        assert image_artifact.kind == ArtifactKind.IMAGE
        assert image_artifact.mime_type == "image/png"
        assert image_artifact.storage_uri in storage.objects
        assert image_artifact.metadata["source_artifact_id"] == str(saved_text.id)
        assert image_artifact.metadata["renderer_version"] == 2
        assert image_artifact.metadata["font_identity"]["file_name"] == "NotoNaskhArabic[wght].ttf"
        assert len(image_artifact.metadata["font_identity"]["sha256"]) == 64
        assert image_artifact.metadata["background_mode"] == "deterministic_solid"
        assert image_artifact.metadata["ai_asset_identity"] is None
        assert image_artifact.metadata["source_text_sha256"] == hashlib.sha256(approved_text.encode("utf-8")).hexdigest()
        assert image_artifact.resolved_context["product"] == pinned_product
        assert image_artifact.resolved_context["recipe"] == pinned_recipe
        assert image_artifact.resolved_context["output_contract"]["key"] == "CARD_IMAGE_PNG"
        assert image_artifact.resolved_context["output_contract"]["version"] == 1
        assert image_artifact.metadata["source_attribution"] == "المصدر: كتاب الأمثلة — حفظ النص (ص. 11)"
        assert image_artifact.metadata["card_title"] == "النص المعتمد"

        persisted = (await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == image_artifact.id)
        )).scalar_one()
        assert persisted.review_status == "DRAFT"
        assert persisted.artifact_metadata["source_artifact_id"] == str(saved_text.id)
        assert persisted.resolved_context["product"] == pinned_product
        assert persisted.resolved_context["recipe"] == pinned_recipe
        assert persisted.resolved_context["output_contract"]["version"] == 1
        assert persisted.mime_type == "image/png"

        object_count_before_retry = len(storage.objects)
        retried_artifact = await RenderApprovedTextCardCapability(
            storage_factory=lambda: storage
        ).execute(context)
        assert retried_artifact.id == image_artifact.id
        assert len(storage.objects) == object_count_before_retry

        class FakeBackgroundGenerator:
            provider_name = "fake"

            def __init__(self, should_fail: bool = False):
                self.should_fail = should_fail
                self.prompts = []

            async def generate(self, prompt, *, aspect_ratio="4:5", image_size="1K"):
                self.prompts.append(prompt)
                assert approved_text not in prompt
                if self.should_fail:
                    raise RuntimeError("synthetic background provider failure")
                background = BytesIO()
                Image.new("RGB", (320, 240), "#334455").save(background, format="PNG")
                return GeneratedImage(
                    content=background.getvalue(),
                    mime_type="image/png",
                    model="fake-background-v1",
                    provider="fake",
                )

        async def create_job_for_background(fingerprint_char: str) -> UUID:
            next_run_id = uuid4()
            next_claim_id = uuid4()
            session.add(ProductionClaimModel(
                id=next_claim_id,
                source_id=source_id,
                scope="SELECTION",
                request_fingerprint=fingerprint_char * 64,
                request_payload={"source_id": str(source_id), "background_test": fingerprint_char},
            ))
            await session.flush()
            session.add(ProductionJobModel(
                id=next_run_id,
                claim_id=next_claim_id,
                source_id=source_id,
                scope="SELECTION",
                status="RUNNING",
                total_items=1,
            ))
            await session.commit()
            return next_run_id

        ai_run_id = await create_job_for_background("b")
        fake_generator = FakeBackgroundGenerator()
        ai_context = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id, "source_artifact_id": saved_text.id},
            configuration={},
            run_id=ai_run_id,
            resolved_context={"output_contract": image_contract},
            stage_configuration={
                "width": 640, "height": 800, "padding": 40, "font_size": 30,
                "line_spacing": 10, "max_lines": 20, "show_title": True,
                "show_source_attribution": True, "font_family": "naskh",
                "background_mode": "ai_generated",
                "background_prompt": "خلفية فنية تجريدية بلا نص أو حروف",
                "provider": "fal", "model": "fake-background-v1",
                "aspect_ratio": "4:5", "image_size": "1K",
            },
        )
        ai_artifact = await RenderApprovedTextCardCapability(
            storage_factory=lambda: storage,
            image_generator_factory=lambda config: fake_generator,
        ).execute(ai_context)
        assert len(fake_generator.prompts) == 1
        assert ai_artifact.metadata["background_mode"] == "ai_generated"
        assert ai_artifact.metadata["ai_asset_identity"]["provider"] == "fake"
        assert ai_artifact.metadata["ai_asset_identity"]["model"] == "fake-background-v1"
        assert ai_artifact.metadata["ai_asset_identity"]["operation_id"]
        assert len(ai_artifact.metadata["ai_asset_identity"]["sha256"]) == 64
        assert ai_artifact.metadata["source_text_sha256"] == hashlib.sha256(approved_text.encode("utf-8")).hexdigest()

        fallback_run_id = await create_job_for_background("c")
        failing_generator = FakeBackgroundGenerator(should_fail=True)
        fallback_context = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id, "source_artifact_id": saved_text.id},
            configuration={},
            run_id=fallback_run_id,
            resolved_context={"output_contract": image_contract},
            stage_configuration={
                "width": 640, "height": 800, "padding": 40, "font_size": 30,
                "line_spacing": 10, "max_lines": 20, "font_family": "naskh",
                "background_mode": "ai_generated",
                "background_prompt": "خلفية فنية تجريدية بلا نص أو حروف",
                "provider": "fal", "model": "fake-background-v1",
            },
        )
        fallback_artifact = await RenderApprovedTextCardCapability(
            storage_factory=lambda: storage,
            image_generator_factory=lambda config: failing_generator,
        ).execute(fallback_context)
        assert fallback_artifact.metadata["background_mode"] == "ai_failed_fallback_solid"
        assert fallback_artifact.metadata["background_generation_status"] == "FALLBACK_TO_SOLID"
        assert fallback_artifact.metadata["ai_asset_identity"] is None
        failure_provenance = fallback_artifact.metadata["background_generation_failure"]
        assert failure_provenance["operation_id"]
        assert failure_provenance["provider"] == "fake"
        assert failure_provenance["model"] == "fake-background-v1"
        assert failure_provenance["adapter"] == "FakeBackgroundGenerator"
        assert failure_provenance["status"] == "FALLBACK_TO_SOLID"
        assert fallback_artifact.metadata["source_text_sha256"] == hashlib.sha256(approved_text.encode("utf-8")).hexdigest()

        factory_failure_run_id = await create_job_for_background("d")
        def fail_background_factory(_configuration):
            raise RuntimeError("synthetic adapter initialization failure")

        factory_failure_context = ProductionExecutionContext(
            session=session,
            inputs={"knowledge_unit_id": unit_id, "source_artifact_id": saved_text.id},
            configuration={},
            run_id=factory_failure_run_id,
            resolved_context=image_resolved_context,
            stage_configuration={
                "width": 640, "height": 800, "padding": 40, "font_size": 30,
                "line_spacing": 10, "max_lines": 20, "font_family": "naskh",
                "background_mode": "ai_generated",
                "background_prompt": "خلفية فنية تجريدية بلا نص أو حروف",
                "provider": "fal", "model": "fake-background-v1",
            },
        )
        factory_failure_artifact = await RenderApprovedTextCardCapability(
            storage_factory=lambda: storage,
            image_generator_factory=fail_background_factory,
        ).execute(factory_failure_context)
        factory_failure = factory_failure_artifact.metadata["background_generation_failure"]
        assert factory_failure["provider"] == "fal"
        assert factory_failure["model"] == "fake-background-v1"
        assert factory_failure["adapter"] is None
        assert factory_failure["operation_id"]
        assert factory_failure_artifact.metadata["source_text_sha256"] == hashlib.sha256(approved_text.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_migrations_seed_four_published_versioned_design_card_products():
    expected_keys = {
        "ARABIC_QUOTE_CARD",
        "ARABIC_TEXT_SOURCE_CARD",
        "ARABIC_POETRY_CARD",
        "ARABIC_ARTISTIC_CARD",
    }
    async with SessionFactory() as session:
        rows = (await session.execute(text("""
            SELECT p.key, pv.definition
            FROM production_products AS p
            JOIN production_product_versions AS pv ON pv.product_id = p.id
            WHERE pv.status = 'PUBLISHED' AND p.key IN (
                'ARABIC_QUOTE_CARD',
                'ARABIC_TEXT_SOURCE_CARD',
                'ARABIC_POETRY_CARD',
                'ARABIC_ARTISTIC_CARD'
            )
        """))).all()
        assert {row.key for row in rows} == expected_keys
        for row in rows:
            definition = row.definition
            assert definition["component_versions"]["output_contract"]["key"] == "IMAGE_ARTIFACT"
            recipe_component = definition["component_versions"]["recipe"]
            recipe_row = (await session.execute(text("""
                SELECT rv.status, rv.definition
                FROM production_recipe_versions AS rv
                WHERE rv.id = :version_id
            """), {"version_id": UUID(recipe_component["version_id"])})).one()
            assert recipe_row.status == "PUBLISHED"
            stage = recipe_row.definition["stages"][0]
            assert stage["capability_key"] == "render_approved_text_card"
            assert stage["capability_version"] == 1
            if row.key == "ARABIC_ARTISTIC_CARD":
                assert stage["configuration"]["background_mode"] == "ai_generated"
                assert stage["configuration"]["provider"] == "fal"
                assert stage["configuration"]["model"] == "fal-ai/flux/schnell"


@pytest.mark.asyncio
async def test_visual_artifact_handoff_api_requires_approved_image_and_matching_approved_text():
    source_id, unit_id, post_id = uuid4(), uuid4(), uuid4()
    text_artifact_id, image_artifact_id = uuid4(), uuid4()
    approved_text = "نص معتمد يجب أن يطابق المنشور حرفيًا."
    source_text_hash = hashlib.sha256(approved_text.encode("utf-8")).hexdigest()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id,
            filename="handoff.pdf",
            mime_type="application/pdf",
            storage_path=f"./storage/test/{source_id}.pdf",
            size_bytes=10,
            status="STORED",
            book_title="كتاب التسليم",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id,
            source_id=source_id,
            position=1,
            title="مادة التسليم",
            content="مادة المصدر",
        ))
        session.add(PostModel(
            id=post_id,
            knowledge_unit_id=unit_id,
            content=approved_text,
            status="APPROVED",
        ))
        await session.flush()
        session.add(ArtifactModel(
            id=text_artifact_id,
            source_knowledge_unit_id=unit_id,
            kind="TEXT",
            status="AVAILABLE",
            content=approved_text,
            mime_type="text/plain",
            output_contract_key="TEXT_ARTIFACT",
            output_contract_version=1,
            resolved_context={},
            artifact_metadata={"title": "نص التسليم"},
            review_status="APPROVED",
        ))
        session.add(ArtifactModel(
            id=image_artifact_id,
            source_knowledge_unit_id=unit_id,
            kind="IMAGE",
            status="AVAILABLE",
            storage_uri=f"s3://test-bucket/{image_artifact_id}.png",
            mime_type="image/png",
            output_contract_key="IMAGE_ARTIFACT",
            output_contract_version=1,
            resolved_context={},
            artifact_metadata={
                "source_artifact_id": str(text_artifact_id),
                "source_text_sha256": source_text_hash,
            },
            review_status="DRAFT",
        ))
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unapproved = await client.post(
            f"/posts/{post_id}/visual-artifact",
            json={"artifact_id": str(image_artifact_id)},
        )
    assert unapproved.status_code == 409

    async with SessionFactory() as session:
        visual = (await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == image_artifact_id)
        )).scalar_one()
        visual.review_status = "APPROVED"
        visual.review_note = "اعتماد بصري مستقل"
        await session.commit()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        attached = await client.post(
            f"/posts/{post_id}/visual-artifact",
            json={"artifact_id": str(image_artifact_id)},
        )
    assert attached.status_code == 200
    assert attached.json()["visual_artifact_id"] == str(image_artifact_id)
