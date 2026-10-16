from app.application.control_plane import ControlPlaneResolver
from app.domain.output_contracts import OutputContractDefinition
from app.domain.products import ProductionProductDefinition
from app.domain.recipes import SUPPORTED_RECIPE_CAPABILITIES
from app.infrastructure.database.session import SessionFactory


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
