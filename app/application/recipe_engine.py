"""Bounded recipe execution over explicitly registered capabilities."""
from collections.abc import Mapping
from dataclasses import dataclass, field as dataclass_field, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.artifacts import ensure_post_artifact, persist_generic_artifact
from app.application.control_plane import ControlPlaneResolver
from app.application.posts import DraftKnowledgeUnitText, ProducePost
from app.adapters.generation.gemini_image import GeminiImageGenerator
from app.domain.image_generation import IImageGenerator
from app.domain.products import ProductionProductDefinition
from app.domain.storage import ObjectStorage
from app.infrastructure.storage import S3CompatibleObjectStorage
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.domain.output_contracts import OutputContractDefinition
from app.domain.production_context import PinnedOutputContract
from app.domain.recipes import ProductionRecipe, validate_recipe_stage_configuration


@dataclass(frozen=True)
class ProductionExecutionContext:
    session: AsyncSession
    inputs: Mapping[str, object]
    configuration: Mapping[str, object]
    run_id: UUID | None = None
    resolved_context: Mapping[str, object] | None = None
    stage_configuration: Mapping[str, object] = dataclass_field(default_factory=dict)


class RecipeCapability(Protocol):
    key: str
    version: int

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None,
    ) -> object: ...


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[tuple[str, int], RecipeCapability] = {}

    def register(self, capability: RecipeCapability) -> None:
        identity = (capability.key, capability.version)
        if identity in self._capabilities:
            raise ValueError(f"Capability '{capability.key}' v{capability.version} is already registered.")
        self._capabilities[identity] = capability

    def resolve(self, key: str, version: int) -> RecipeCapability:
        capability = self._capabilities.get((key, version))
        if capability is None:
            raise LookupError(f"Recipe capability '{key}' v{version} is not registered.")
        return capability


def _stage_system_prompt(context: ProductionExecutionContext, capability_key: str) -> str:
    editorial_prompt = context.configuration.get("editorial_prompt")
    if not isinstance(editorial_prompt, Mapping) or not isinstance(editorial_prompt.get("body"), str):
        raise ValueError(f"{capability_key} capability requires a resolved editorial_prompt body.")
    system_prompt = editorial_prompt["body"]
    style_instructions = context.stage_configuration.get("style_instructions")
    if style_instructions is not None:
        if not isinstance(style_instructions, str) or not style_instructions.strip():
            raise ValueError(f"{capability_key} style_instructions must be a non-empty string.")
        system_prompt = f"{system_prompt}\n\nRecipe-specific instructions:\n{style_instructions.strip()}"
    return system_prompt


class ProducePostCapability:
    key = "produce_post"
    version = 1

    def __init__(self, drafter, resolver: ControlPlaneResolver | None = None) -> None:
        self.producer = ProducePost(drafter, resolver or ControlPlaneResolver())

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None = None,
    ) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_post capability requires a knowledge_unit_id input.")
        system_prompt = _stage_system_prompt(context, self.key)
        post = await self.producer.execute(
            context.session,
            knowledge_unit_id,
            system_prompt=system_prompt,
        )
        return await ensure_post_artifact(
            context.session,
            post,
            production_job_id=context.run_id,
            resolved_context=(
                dict(context.resolved_context)
                if context.resolved_context is not None
                else None
            ),
        )


class ProduceTextArtifactCapability:
    key = "produce_text_artifact"
    version = 1

    def __init__(self, drafter, resolver: ControlPlaneResolver | None = None) -> None:
        self.generator = DraftKnowledgeUnitText(drafter, resolver or ControlPlaneResolver())

    async def execute(
        self,
        context: ProductionExecutionContext,
        previous_output: object | None = None,
    ) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_text_artifact capability requires a knowledge_unit_id input.")
        if context.resolved_context is None or "output_contract" not in context.resolved_context:
            raise ValueError("produce_text_artifact capability requires a pinned output contract.")
        pinned_contract = PinnedOutputContract.from_dict(context.resolved_context["output_contract"])
        contract = OutputContractDefinition.from_dict(pinned_contract.definition)
        drafted = await self.generator.execute(
            context.session, knowledge_unit_id, system_prompt=_stage_system_prompt(context, self.key)
        )
        now = datetime.now(timezone.utc)
        artifact = Artifact(
            id=uuid4(),
            source_knowledge_unit_id=knowledge_unit_id,
            kind=ArtifactKind.TEXT,
            content=drafted.content,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            mime_type=contract.mime_type,
            production_job_id=context.run_id,
            output_contract_key=pinned_contract.key,
            output_contract_version=pinned_contract.version,
            resolved_context=dict(context.resolved_context),
            metadata={"title": drafted.title},
        )
        return await persist_generic_artifact(
            context.session, artifact, resolved_context=dict(context.resolved_context)
        )


class ProduceImageArtifactCapability:
    key = "produce_image_artifact"
    version = 1

    def __init__(self, drafter, resolver: ControlPlaneResolver | None = None,
                 image_generator: IImageGenerator | None = None,
                 object_storage: ObjectStorage | None = None) -> None:
        self.generator = DraftKnowledgeUnitText(drafter, resolver or ControlPlaneResolver())
        self.image_generator = image_generator or GeminiImageGenerator()
        self.object_storage = object_storage

    async def execute(self, context: ProductionExecutionContext, previous_output: object | None = None) -> Artifact:
        knowledge_unit_id = context.inputs.get("knowledge_unit_id")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_image_artifact capability requires a knowledge_unit_id input.")
        if context.resolved_context is None or "output_contract" not in context.resolved_context:
            raise ValueError("produce_image_artifact capability requires a pinned output contract.")
        pinned_contract = PinnedOutputContract.from_dict(context.resolved_context["output_contract"])
        contract = OutputContractDefinition.from_dict(pinned_contract.definition)
        product_snapshot = context.resolved_context.get("product")
        if not isinstance(product_snapshot, Mapping) or not isinstance(product_snapshot.get("definition"), Mapping):
            raise ValueError("produce_image_artifact capability requires a pinned Product definition.")
        product_definition = ProductionProductDefinition.from_dict(product_snapshot["definition"])
        drafted = await self.generator.execute(
            context.session, knowledge_unit_id, system_prompt=_stage_system_prompt(context, self.key)
        )
        prompt = (
            "Create one original editorial image to accompany the following source-grounded Arabic literary content. "
            "Use a refined, culturally respectful visual composition. Do not invent factual details, add logos, "
            "or render text inside the image.\n\n"
            f"Audience: {product_definition.audience}\n"
            f"Desired experience: {product_definition.experience}\n"
            f"Source title: {drafted.title}\n"
            f"Editorial content:\n{drafted.content}"
        )
        image = await self.image_generator.generate(prompt, aspect_ratio="1:1", image_size="1K")
        storage = self.object_storage or S3CompatibleObjectStorage.from_env()
        storage_uri = await storage.save(
            filename=f"{drafted.title}.png", content=image.data,
            prefix=str(context.run_id or uuid4()), mime_type=image.mime_type,
        )
        now = datetime.now(timezone.utc)
        artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=knowledge_unit_id, kind=ArtifactKind.IMAGE,
            content=None, status=ArtifactStatus.AVAILABLE.value, created_at=now, updated_at=now,
            storage_uri=storage_uri, mime_type=image.mime_type, production_job_id=context.run_id,
            output_contract_key=pinned_contract.key, output_contract_version=pinned_contract.version,
            resolved_context=dict(context.resolved_context),
            metadata={"title": drafted.title, "alt_text": f"صورة تحريرية مرتبطة بمادة: {drafted.title}"},
        )
        return await persist_generic_artifact(context.session, artifact, resolved_context=dict(context.resolved_context))


class ProductionRecipeEngine:
    def __init__(self, capabilities: CapabilityRegistry) -> None:
        self.capabilities = capabilities

    def validate_recipe(self, pinned_recipe: ProductionRecipe) -> None:
        # The persisted snapshot is the recipe source of truth for this run.
        # Only registered capability implementations may execute its declarative stages.
        for stage in pinned_recipe.stages:
            self.capabilities.resolve(stage.capability_key, stage.capability_version)
            validate_recipe_stage_configuration(stage)

    async def execute(
        self,
        pinned_recipe: ProductionRecipe,
        context: ProductionExecutionContext,
    ) -> Artifact:
        self.validate_recipe(pinned_recipe)
        output: object | None = None
        for stage in pinned_recipe.stages:
            capability = self.capabilities.resolve(
                stage.capability_key, stage.capability_version
            )
            stage_context = replace(context, stage_configuration=stage.configuration)
            output = await capability.execute(stage_context, output)

        if not isinstance(output, Artifact):
            raise TypeError("The final recipe stage must return a validated Artifact.")
        return output


def build_production_recipe_engine(
    drafter,
    resolver: ControlPlaneResolver | None = None,
    *,
    image_generator: IImageGenerator | None = None,
    object_storage: ObjectStorage | None = None,
) -> ProductionRecipeEngine:
    capabilities = CapabilityRegistry()
    capabilities.register(ProducePostCapability(drafter, resolver))
    capabilities.register(ProduceTextArtifactCapability(drafter, resolver))
    capabilities.register(ProduceImageArtifactCapability(drafter, resolver, image_generator, object_storage))
    return ProductionRecipeEngine(capabilities=capabilities)
