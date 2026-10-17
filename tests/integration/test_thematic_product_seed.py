from app.application.control_plane import ControlPlaneResolver
from app.domain.output_contracts import OutputContractDefinition
from app.domain.products import ProductionProductDefinition
from app.domain.recipes import SUPPORTED_RECIPE_CAPABILITIES
from app.infrastructure.database.session import SessionFactory
from app.application.production_jobs import create_production_job
from app.domain.production_jobs import ProductionScope
from app.infrastructure.database.models import KnowledgeUnitModel, ProductionClaimModel, SourceModel
from sqlalchemy import select
from uuid import uuid4


async def test_seeded_thematic_product_pins_a_supported_recipe_and_text_contract():
    async with SessionFactory() as session:
        resolver = ControlPlaneResolver()
        product = await resolver.resolve_product(session, "ARABIC_LITERATURE_THEMATIC_TEXT")
        definition = ProductionProductDefinition.from_dict(product.definition)
        assert definition.has_immutable_manifest
        refs = definition.component_versions
        assert refs is not None

        recipe = await resolver.resolve_recipe_version(session, refs["recipe"])
        assert recipe.key == "BOOK_TO_THEMATIC_TEXT_ARTIFACT"
        assert len(recipe.stages) == 1
        assert (recipe.stages[0].capability_key, recipe.stages[0].capability_version) in SUPPORTED_RECIPE_CAPABILITIES

        contract = await resolver.resolve_output_contract_version(session, refs["output_contract"])
        contract_definition = OutputContractDefinition.from_dict(contract.definition)
        assert contract_definition.artifact_kind == "TEXT"
        assert contract_definition.content_mode == "INLINE"
        assert contract_definition.mime_type == "text/plain"



async def test_thematic_claim_preserves_explicit_source_order():
    first_source_id, second_source_id = uuid4(), uuid4()
    first_unit_id, second_unit_id = uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add_all([
            SourceModel(
                id=first_source_id, filename="first.pdf", mime_type="application/pdf",
                storage_path="./storage/test/first.pdf", size_bytes=10, status="STORED",
            ),
            SourceModel(
                id=second_source_id, filename="second.pdf", mime_type="application/pdf",
                storage_path="./storage/test/second.pdf", size_bytes=10, status="STORED",
            ),
            KnowledgeUnitModel(
                id=first_unit_id, source_id=first_source_id, position=1,
                title="First selected", content="First source content",
            ),
            KnowledgeUnitModel(
                id=second_unit_id, source_id=second_source_id, position=1,
                title="Second selected", content="Second source content",
            ),
        ])
        await session.commit()

        job = await create_production_job(
            session,
            first_source_id,
            ProductionScope.SELECTION,
            knowledge_unit_ids=[first_unit_id, second_unit_id],
            product_key="ARABIC_LITERATURE_THEMATIC_TEXT",
            thematic_theme="موضوع اختباري",
        )
        claim = (await session.execute(
            select(ProductionClaimModel).where(ProductionClaimModel.id == job.claim_id)
        )).scalar_one()
        assert claim.request_payload["knowledge_unit_ids"] == [
            str(first_unit_id), str(second_unit_id)
        ]
