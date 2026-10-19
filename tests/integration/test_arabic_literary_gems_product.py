from app.application.control_plane import ControlPlaneResolver
from app.domain.output_contracts import OutputContractDefinition
from app.domain.policies import ProductionPolicyDefinition
from app.domain.products import ProductionProductDefinition
from app.domain.recipes import SUPPORTED_RECIPE_CAPABILITIES
from app.infrastructure.database.session import SessionFactory


async def test_arabic_literary_gems_is_a_published_immutable_product():
    async with SessionFactory() as session:
        resolver = ControlPlaneResolver()
        product = await resolver.resolve_product(session, "ARABIC_LITERARY_GEMS")
        definition = ProductionProductDefinition.from_dict(product.definition)

        assert product.status == "PUBLISHED"
        assert definition.has_immutable_manifest
        assert definition.prompt_key == "ARABIC_LITERARY_GEMS_DRAFTER"
        assert definition.identity_key == "ARABIC_LITERARY_EDITOR"

        refs = definition.component_versions
        assert refs is not None
        prompt = await resolver.resolve_prompt_version(session, refs["prompt"])
        identity = await resolver.resolve_identity_version(session, refs["identity"])
        recipe = await resolver.resolve_recipe_version(session, refs["recipe"])
        policy = await resolver.resolve_policy_version(session, refs["policy"])
        contract = await resolver.resolve_output_contract_version(session, refs["output_contract"])

        assert prompt.key == "ARABIC_LITERARY_GEMS_DRAFTER"
        assert "لا تختلق نصًا أو مصدرًا أو نسبة" in prompt.body
        assert "{{" not in prompt.body
        assert identity.key == "ARABIC_LITERARY_EDITOR"
        assert "النص الأصلي مقدم على التعليق عليه." in identity.definition["principles"]
        assert policy.key == "ARABIC_LITERARY_EDITORIAL_POLICY"
        assert ProductionPolicyDefinition.from_dict(policy.definition).allow_urls is False
        assert recipe.key == "ARABIC_LITERARY_POST_V1"
        assert len(recipe.stages) == 1
        stage = recipe.stages[0]
        assert (stage.capability_key, stage.capability_version) == ("produce_text_artifact", 1)
        assert (stage.capability_key, stage.capability_version) in SUPPORTED_RECIPE_CAPABILITIES
        assert stage.configuration["style_instructions"]
        contract_definition = OutputContractDefinition.from_dict(contract.definition)
        assert contract_definition.artifact_kind == "TEXT"
        assert contract_definition.content_mode == "INLINE"
        assert contract_definition.mime_type == "text/plain"
