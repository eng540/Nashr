from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.control_plane import PromptTemplate, ResolvedPrompt
from app.domain.recipes import ProductionRecipe, RecipeStage
from app.domain.production_context import PinnedIdentity, PinnedOutputContract, PinnedPolicy, PinnedProduct
from app.domain.identities import EditorialIdentityDefinition
from app.infrastructure.database.identities import EditorialIdentityRepository
from app.infrastructure.database.control_plane import PromptTemplateRepository
from app.infrastructure.database.recipes import ProductionRecipeRepository
from app.infrastructure.database.output_contracts import OutputContractRepository
from app.domain.output_contracts import OutputContractDefinition
from app.domain.policies import ProductionPolicyDefinition
from app.domain.products import ProductionProductDefinition
from app.infrastructure.database.policies import ProductionPolicyRepository
from app.infrastructure.database.products import ProductionProductRepository
from app.infrastructure.database.models import (
    EditorialIdentityModel, EditorialIdentityVersionModel,
    OutputContractModel, OutputContractVersionModel,
    ProductionPolicyModel, ProductionPolicyVersionModel,
    ProductionRecipeModel, ProductionRecipeVersionModel,
    PromptTemplateModel, PromptTemplateVersionModel,
)
from uuid import UUID
import re
from sqlalchemy import select


EDITORIAL_PROMPT_KEY = "editorial.drafter"

DISCOVERY_PROMPT_REQUIRED_VARIABLES = {
    "knowledge.book_map.section": {"window_page_count", "page_start", "page_end"},
    "knowledge.book_map.merge": {"page_count", "round_index", "batch_index", "section_count", "payload"},
    "knowledge.material_discovery.context": {
        "source_name", "topic_title", "topic_description", "page_start", "page_end",
    },
}


def validate_prompt_template_body(key: str, body: str) -> None:
    """Reject malformed editable templates before publishing them into an active pipeline."""
    if not isinstance(body, str) or not body.strip():
        raise ValueError("Prompt body cannot be empty.")
    required = DISCOVERY_PROMPT_REQUIRED_VARIABLES.get(key)
    if required is None:
        return
    found = set(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", body))
    missing = required - found
    unsupported = found - required
    if missing:
        raise ValueError(
            f"Prompt template '{key}' is missing required variables: " + ", ".join(sorted(missing))
        )
    if unsupported:
        raise ValueError(
            f"Prompt template '{key}' contains unsupported variables: " + ", ".join(sorted(unsupported))
        )


class ControlPlaneResolver:
    async def resolve_prompt(self, session: AsyncSession, key: str):
        return await PromptTemplateRepository(session).resolve_active(key)

    async def resolve_recipe(self, session: AsyncSession, key: str):
        return await ProductionRecipeRepository(session).resolve_active(key)

    async def resolve_prompt_version(self, session: AsyncSession, reference: dict[str, object]) -> ResolvedPrompt:
        version_id = UUID(str(reference["version_id"]))
        result = await session.execute(
            select(PromptTemplateModel, PromptTemplateVersionModel)
            .join(PromptTemplateVersionModel, PromptTemplateVersionModel.prompt_template_id == PromptTemplateModel.id)
            .where(PromptTemplateModel.key == reference["key"],
                   PromptTemplateVersionModel.id == version_id,
                   PromptTemplateVersionModel.status.in_(("PUBLISHED", "ARCHIVED")))
        )
        row = result.one_or_none()
        if row is None or row[1].version != reference["version"]:
            raise LookupError("Pinned product prompt version is unavailable or does not match its manifest.")
        return ResolvedPrompt(key=row[0].key, version=row[1].version, body=row[1].body,
                              template_id=row[0].id, version_id=row[1].id)

    async def resolve_recipe_version(self, session: AsyncSession, reference: dict[str, object]) -> ProductionRecipe:
        version_id = UUID(str(reference["version_id"]))
        result = await session.execute(
            select(ProductionRecipeModel, ProductionRecipeVersionModel)
            .join(ProductionRecipeVersionModel, ProductionRecipeVersionModel.recipe_id == ProductionRecipeModel.id)
            .where(ProductionRecipeModel.key == reference["key"],
                   ProductionRecipeVersionModel.id == version_id,
                   ProductionRecipeVersionModel.status.in_(("PUBLISHED", "ARCHIVED")))
        )
        row = result.one_or_none()
        if row is None or row[1].version != reference["version"]:
            raise LookupError("Pinned product recipe version is unavailable or does not match its manifest.")
        stages = row[1].definition.get("stages")
        if not isinstance(stages, list):
            raise ValueError("Pinned product recipe has an invalid stage definition.")
        return ProductionRecipe(key=row[0].key, version=row[1].version,
                                stages=tuple(RecipeStage.from_dict(stage) for stage in stages),
                                recipe_id=str(row[0].id), version_id=str(row[1].id))

    async def resolve_identity_version(self, session: AsyncSession, reference: dict[str, object]) -> PinnedIdentity:
        version_id = UUID(str(reference["version_id"]))
        result = await session.execute(
            select(EditorialIdentityModel, EditorialIdentityVersionModel)
            .join(EditorialIdentityVersionModel, EditorialIdentityVersionModel.identity_id == EditorialIdentityModel.id)
            .where(EditorialIdentityModel.key == reference["key"],
                   EditorialIdentityVersionModel.id == version_id,
                   EditorialIdentityVersionModel.status.in_(("PUBLISHED", "ARCHIVED")))
        )
        row = result.one_or_none()
        if row is None or row[1].version != reference["version"]:
            raise LookupError("Pinned product identity version is unavailable or does not match its manifest.")
        return PinnedIdentity(identity_id=str(row[0].id), version_id=str(row[1].id), key=row[0].key,
                              version=row[1].version,
                              definition=EditorialIdentityDefinition.from_dict(row[1].definition).to_dict())

    async def resolve_policy_version(self, session: AsyncSession, reference: dict[str, object]) -> PinnedPolicy:
        version_id = UUID(str(reference["version_id"]))
        result = await session.execute(
            select(ProductionPolicyModel, ProductionPolicyVersionModel)
            .join(ProductionPolicyVersionModel, ProductionPolicyVersionModel.policy_id == ProductionPolicyModel.id)
            .where(ProductionPolicyModel.key == reference["key"],
                   ProductionPolicyVersionModel.id == version_id,
                   ProductionPolicyVersionModel.status.in_(("PUBLISHED", "ARCHIVED")))
        )
        row = result.one_or_none()
        if row is None or row[1].version != reference["version"]:
            raise LookupError("Pinned product policy version is unavailable or does not match its manifest.")
        return PinnedPolicy(policy_id=str(row[0].id), version_id=str(row[1].id), key=row[0].key,
                            version=row[1].version,
                            definition=ProductionPolicyDefinition.from_dict(row[1].definition).to_dict())

    async def resolve_output_contract_version(self, session: AsyncSession, reference: dict[str, object]) -> PinnedOutputContract:
        version_id = UUID(str(reference["version_id"]))
        result = await session.execute(
            select(OutputContractModel, OutputContractVersionModel)
            .join(OutputContractVersionModel, OutputContractVersionModel.contract_id == OutputContractModel.id)
            .where(OutputContractModel.key == reference["key"],
                   OutputContractVersionModel.id == version_id,
                   OutputContractVersionModel.status.in_(("PUBLISHED", "ARCHIVED")))
        )
        row = result.one_or_none()
        if row is None or row[1].version != reference["version"]:
            raise LookupError("Pinned product output-contract version is unavailable or does not match its manifest.")
        return PinnedOutputContract(contract_id=str(row[0].id), version_id=str(row[1].id), key=row[0].key,
                                    version=row[1].version,
                                    definition=OutputContractDefinition.from_dict(row[1].definition).to_dict())

    async def resolve_output_contract(self, session: AsyncSession, key: str) -> PinnedOutputContract:
        contract, version = await OutputContractRepository(session).resolve_active(key)
        return PinnedOutputContract(
            contract_id=str(contract.id),
            version_id=str(version.id),
            key=contract.key,
            version=version.version,
            definition=OutputContractDefinition.from_dict(version.definition).to_dict(),
        )

    async def resolve_product(self, session: AsyncSession, key: str) -> PinnedProduct:
        product, version = await ProductionProductRepository(session).resolve_active(key)
        return PinnedProduct(
            product_id=str(product.id), version_id=str(version.id), key=product.key,
            version=version.version,
            definition=ProductionProductDefinition.from_dict(version.definition).to_dict(),
        )

    async def resolve_policy(self, session: AsyncSession, key: str) -> PinnedPolicy:
        policy, version = await ProductionPolicyRepository(session).resolve_active(key)
        return PinnedPolicy(
            policy_id=str(policy.id), version_id=str(version.id), key=policy.key,
            version=version.version, definition=ProductionPolicyDefinition.from_dict(version.definition).to_dict(),
        )

    async def resolve_identity(self, session: AsyncSession, key: str) -> PinnedIdentity:
        identity, version = await EditorialIdentityRepository(session).resolve_active(key)
        return PinnedIdentity(
            identity_id=str(identity.id),
            version_id=str(version.id),
            key=identity.key,
            version=version.version,
            definition=EditorialIdentityDefinition.from_dict(version.definition).to_dict(),
        )


class PromptTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = PromptTemplateRepository(session)

    async def list_templates(self):
        return await self.repository.list_templates()

    async def get_template(self, key: str):
        row = await self.repository.get_template(key)
        if row is None:
            raise LookupError("Prompt template not found.")
        template = PromptTemplate(
            id=row.id,
            key=row.key,
            name=row.name,
            purpose=row.purpose,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        return template, await self.repository.get_versions(key)

    async def create_template(self, key: str, name: str, purpose: str, body: str):
        validate_prompt_template_body(key.strip(), body)
        if await self.repository.get_template(key):
            raise ValueError("Prompt template key already exists.")
        template = await self.repository.create_template(key.strip(), name.strip(), purpose.strip())
        model = await self.repository.get_template(key.strip())
        version = await self.repository.create_version(model, body)
        await self.repository.session.commit()
        return template, version

    async def create_draft(self, key: str, body: str):
        validate_prompt_template_body(key, body)
        template = await self.repository.get_template(key)
        if template is None:
            raise LookupError("Prompt template not found.")
        result = await self.repository.create_version(template, body)
        await self.repository.session.commit()
        return result

    async def update_draft(self, key: str, version: int, body: str):
        validate_prompt_template_body(key, body)
        result = await self.repository.update_draft(key, version, body)
        await self.repository.session.commit()
        return result

    async def publish(self, key: str, version: int):
        versions = await self.repository.get_versions(key)
        target = next((item for item in versions if item.version == version), None)
        if target is None:
            raise LookupError("Prompt template version not found.")
        validate_prompt_template_body(key, target.body)
        result = await self.repository.publish(key, version)
        await self.repository.session.commit()
        return result

    async def archive(self, key: str, version: int):
        result = await self.repository.archive(key, version)
        await self.repository.session.commit()
        return result
