"""Bounded recipe execution over explicitly registered capabilities."""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.artifacts import post_to_artifact
from app.application.control_plane import ControlPlaneResolver
from app.application.posts import ProducePost
from app.domain.artifacts import Artifact
from app.domain.recipes import BOOK_TO_TELEGRAM_POST, ProductionRecipe


@dataclass(frozen=True)
class ProductionExecutionContext:
    session: AsyncSession
    inputs: Mapping[str, object]
    configuration: Mapping[str, object]


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


class RecipeRegistry:
    def __init__(self, recipes: tuple[ProductionRecipe, ...] = ()) -> None:
        self._recipes: dict[tuple[str, int], ProductionRecipe] = {}
        for recipe in recipes:
            self.register(recipe)

    def register(self, recipe: ProductionRecipe) -> None:
        identity = (recipe.key, recipe.version)
        if identity in self._recipes:
            raise ValueError(f"Recipe '{recipe.key}' v{recipe.version} is already registered.")
        self._recipes[identity] = recipe

    def resolve(self, key: str, version: int) -> ProductionRecipe:
        recipe = self._recipes.get((key, version))
        if recipe is None:
            raise LookupError(f"Recipe '{key}' v{version} is not registered.")
        return recipe


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
        post = await self.producer.execute(
            context.session,
            knowledge_unit_id,
            system_prompt=editorial_prompt["body"],
        )
        return post_to_artifact(post)


class ProductionRecipeEngine:
    def __init__(self, recipes: RecipeRegistry, capabilities: CapabilityRegistry) -> None:
        self.recipes = recipes
        self.capabilities = capabilities

    async def execute(
        self,
        pinned_recipe: ProductionRecipe,
        context: ProductionExecutionContext,
    ) -> Artifact:
        registered = self.recipes.resolve(pinned_recipe.key, pinned_recipe.version)
        if registered != pinned_recipe:
            raise LookupError(
                f"Pinned recipe '{pinned_recipe.key}' v{pinned_recipe.version} "
                "does not match the registered immutable definition."
            )

        output: object | None = None
        for stage in pinned_recipe.stages:
            capability = self.capabilities.resolve(
                stage.capability_key, stage.capability_version
            )
            output = await capability.execute(context, output)

        if not isinstance(output, Artifact):
            raise TypeError("The final recipe stage must return a validated Artifact.")
        return output


def build_book_to_telegram_post_engine(
    drafter,
    resolver: ControlPlaneResolver | None = None,
) -> ProductionRecipeEngine:
    capabilities = CapabilityRegistry()
    capabilities.register(ProducePostCapability(drafter, resolver))
    return ProductionRecipeEngine(
        recipes=RecipeRegistry((BOOK_TO_TELEGRAM_POST,)),
        capabilities=capabilities,
    )
