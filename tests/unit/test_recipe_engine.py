from uuid import uuid4

import pytest

from app.application.recipe_engine import (
    CapabilityRegistry,
    ProductionExecutionContext,
    ProductionRecipeEngine,
    RecipeRegistry,
)
from app.domain.artifacts import Artifact, ArtifactKind
from app.domain.recipes import BOOK_TO_TELEGRAM_POST, ProductionRecipe, RecipeStage


class RecordingCapability:
    key = "test_capability"
    version = 1

    def __init__(self, output):
        self.output = output
        self.calls = []

    async def execute(self, context, previous_output):
        self.calls.append((context.knowledge_unit_id, previous_output))
        return self.output


@pytest.mark.asyncio
async def test_recipe_engine_runs_registered_stages_in_order():
    first = RecordingCapability("intermediate")
    first.key = "first"
    second = RecordingCapability(Artifact(
        id=uuid4(),
        source_knowledge_unit_id=uuid4(),
        kind=ArtifactKind.POST,
        content="draft",
        status="DRAFT",
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    ))
    second.key = "second"
    recipe = ProductionRecipe(
        key="TEST_RECIPE",
        version=1,
        stages=(
            RecipeStage("first-stage", "first", 1),
            RecipeStage("second-stage", "second", 1),
        ),
    )
    capabilities = CapabilityRegistry()
    capabilities.register(first)
    capabilities.register(second)
    engine = ProductionRecipeEngine(RecipeRegistry((recipe,)), capabilities)
    context = ProductionExecutionContext(
        session=None,
        knowledge_unit_id=uuid4(),
        system_prompt="pinned prompt",
    )

    result = await engine.execute(recipe, context)

    assert result is second.output
    assert first.calls == [(context.knowledge_unit_id, None)]
    assert second.calls == [(context.knowledge_unit_id, "intermediate")]


@pytest.mark.asyncio
async def test_recipe_engine_rejects_definition_drift_for_a_pinned_version():
    capabilities = CapabilityRegistry()
    engine = ProductionRecipeEngine(RecipeRegistry((BOOK_TO_TELEGRAM_POST,)), capabilities)
    changed_definition = ProductionRecipe(
        key=BOOK_TO_TELEGRAM_POST.key,
        version=BOOK_TO_TELEGRAM_POST.version,
        stages=(RecipeStage("different-stage", "produce_post", 1),),
    )
    context = ProductionExecutionContext(session=None, knowledge_unit_id=uuid4(), system_prompt="p")

    with pytest.raises(LookupError, match="immutable definition"):
        await engine.execute(changed_definition, context)


def test_recipe_definition_round_trips_as_data_and_rejects_empty_stages():
    assert ProductionRecipe.from_dict(BOOK_TO_TELEGRAM_POST.to_dict()) == BOOK_TO_TELEGRAM_POST
    with pytest.raises(ValueError, match="at least one stage"):
        ProductionRecipe(key="EMPTY", version=1, stages=())
