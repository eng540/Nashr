from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.recipe_engine import (
    CapabilityRegistry,
    ProductionExecutionContext,
    ProductionRecipeEngine,
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
        self.calls.append((context.inputs["knowledge_unit_id"], previous_output))
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
        status="AVAILABLE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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
    engine = ProductionRecipeEngine(capabilities)
    context = ProductionExecutionContext(
        session=None,
        inputs={"knowledge_unit_id": uuid4()},
        configuration={"editorial_prompt": {"body": "pinned prompt"}},
    )

    result = await engine.execute(recipe, context)

    assert result is second.output
    assert first.calls == [(context.inputs["knowledge_unit_id"], None)]
    assert second.calls == [(context.inputs["knowledge_unit_id"], "intermediate")]


@pytest.mark.asyncio
async def test_recipe_engine_rejects_unregistered_capabilities_from_recipe_data():
    capabilities = CapabilityRegistry()
    engine = ProductionRecipeEngine(capabilities)
    recipe = ProductionRecipe(
        key="DATA_DRIVEN_RECIPE",
        version=1,
        stages=(RecipeStage("unknown-stage", "not_registered", 1),),
    )
    context = ProductionExecutionContext(session=None, inputs={"knowledge_unit_id": uuid4()}, configuration={})

    with pytest.raises(LookupError, match="not registered"):
        await engine.execute(recipe, context)


def test_recipe_definition_round_trips_as_data_and_rejects_empty_stages():
    assert ProductionRecipe.from_dict(BOOK_TO_TELEGRAM_POST.to_dict()) == BOOK_TO_TELEGRAM_POST
    with pytest.raises(ValueError, match="at least one stage"):
        ProductionRecipe(key="EMPTY", version=1, stages=())
