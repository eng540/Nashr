"""Bounded recipe execution over explicitly registered capabilities."""
from collections.abc import Mapping
from dataclasses import dataclass, field as dataclass_field, replace
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.artifacts import ensure_post_artifact
from app.application.control_plane import ControlPlaneResolver
from app.application.posts import ProducePost
from app.domain.artifacts import Artifact
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
        editorial_prompt = context.configuration.get("editorial_prompt")
        if not isinstance(knowledge_unit_id, UUID):
            raise ValueError("produce_post capability requires a knowledge_unit_id input.")
        if not isinstance(editorial_prompt, Mapping) or not isinstance(editorial_prompt.get("body"), str):
            raise ValueError("produce_post capability requires a resolved editorial_prompt body.")
        system_prompt = editorial_prompt["body"]
        style_instructions = context.stage_configuration.get("style_instructions")
        if style_instructions is not None:
            if not isinstance(style_instructions, str) or not style_instructions.strip():
                raise ValueError("produce_post style_instructions must be a non-empty string.")
            system_prompt = f"{system_prompt}\n\nRecipe-specific instructions:\n{style_instructions.strip()}"
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
) -> ProductionRecipeEngine:
    capabilities = CapabilityRegistry()
    capabilities.register(ProducePostCapability(drafter, resolver))
    return ProductionRecipeEngine(capabilities=capabilities)
