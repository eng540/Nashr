import pytest
from uuid import UUID

from app.domain.control_plane import ResolvedPrompt
from app.domain.production_context import (
    LEGACY_PIN_BACKFILL,
    RUNTIME_RESOLUTION,
    ResolvedProductionContext,
)


def test_resolved_prompt_carries_runtime_version_and_body():
    prompt = ResolvedPrompt(key="editorial.drafter", version=3, body="resolved")
    assert prompt.key == "editorial.drafter"
    assert prompt.version == 3
    assert prompt.body == "resolved"


def test_resolved_production_context_round_trips_explicit_prompt_identity():
    prompt = ResolvedPrompt(
        key="editorial.drafter",
        version=3,
        body="resolved prompt body",
        template_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    context = ResolvedProductionContext.capture(prompt)
    restored = ResolvedProductionContext.from_dict(context.to_dict())

    assert restored == context
    assert restored.schema_version == 1
    assert restored.origin == RUNTIME_RESOLUTION
    assert restored.prompt_template.key == "editorial.drafter"
    assert restored.prompt_template.version == 3
    assert restored.prompt_template.body == "resolved prompt body"
    assert restored.prompt_template.template_id == str(prompt.template_id)
    assert restored.prompt_template.version_id == str(prompt.version_id)
    assert restored.captured_at is not None


def test_resolved_production_context_rejects_unknown_schema_and_missing_ids():
    value = {
        "schema_version": 2,
        "origin": RUNTIME_RESOLUTION,
        "captured_at": None,
        "prompt_template": {
            "template_id": "00000000-0000-0000-0000-000000000001",
            "version_id": "00000000-0000-0000-0000-000000000002",
            "key": "editorial.drafter",
            "version": 1,
            "body": "prompt",
        },
    }
    with pytest.raises(ValueError, match="Unsupported"):
        ResolvedProductionContext.from_dict(value)

    value["schema_version"] = 1
    del value["prompt_template"]["version_id"]
    with pytest.raises(ValueError, match="missing version_id"):
        ResolvedProductionContext.from_dict(value)


def test_schema_v2_pins_recipe_key_version_and_stages():
    from app.domain.recipes import BOOK_TO_TELEGRAM_POST

    prompt = ResolvedPrompt(
        key="editorial.drafter",
        version=4,
        body="prompt",
        template_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    context = ResolvedProductionContext.capture(prompt, recipe=BOOK_TO_TELEGRAM_POST)
    restored = ResolvedProductionContext.from_dict(context.to_dict())

    assert restored.schema_version == 2
    assert restored.recipe == BOOK_TO_TELEGRAM_POST
    assert restored.recipe.to_dict()["stages"][0]["capability_key"] == "produce_post"


def test_legacy_backfill_origin_is_distinct_from_runtime_resolution():
    value = {
        "schema_version": 1,
        "origin": LEGACY_PIN_BACKFILL,
        "captured_at": None,
        "prompt_template": {
            "template_id": "00000000-0000-0000-0000-000000000001",
            "version_id": "00000000-0000-0000-0000-000000000002",
            "key": "editorial.drafter",
            "version": 1,
            "body": "prompt",
        },
    }
    context = ResolvedProductionContext.from_dict(value)
    assert context.origin == LEGACY_PIN_BACKFILL
    assert context.captured_at is None
