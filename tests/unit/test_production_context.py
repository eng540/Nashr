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
        "schema_version": 6,
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


@pytest.mark.parametrize("version", [True, 0, -1, 1.5])
def test_pinned_prompt_rejects_invalid_version_types(version):
    from app.domain.production_context import PinnedPrompt

    with pytest.raises(ValueError, match="positive version"):
        PinnedPrompt(
            template_id="00000000-0000-0000-0000-000000000001",
            version_id="00000000-0000-0000-0000-000000000002",
            key="editorial.drafter",
            version=version,
            body="prompt",
        )


def test_resolved_context_rejects_boolean_schema_version():
    from app.domain.production_context import PinnedPrompt

    prompt = PinnedPrompt(
        template_id="00000000-0000-0000-0000-000000000001",
        version_id="00000000-0000-0000-0000-000000000002",
        key="editorial.drafter",
        version=1,
        body="prompt",
    )
    with pytest.raises(ValueError, match="Unsupported resolved production context schema version"):
        ResolvedProductionContext(schema_version=True, origin=RUNTIME_RESOLUTION, captured_at=None, prompt_template=prompt)


def test_schema_v3_pins_identity_definition_and_ids():
    from app.domain.production_context import PinnedIdentity
    from app.domain.recipes import BOOK_TO_TELEGRAM_POST

    prompt = ResolvedPrompt(
        key="editorial.drafter",
        version=5,
        body="base prompt",
        template_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    identity = PinnedIdentity(
        identity_id="00000000-0000-0000-0000-000000000003",
        version_id="00000000-0000-0000-0000-000000000004",
        key="ARABIC_LITERATURE",
        version=2,
        definition={
            "purpose": "Preserve literary heritage",
            "audience": "Arabic readers",
            "voice": "Rooted and clear",
            "tone": "Warm",
            "principles": ["Source fidelity"],
            "objectives": ["Encourage reading"],
            "constraints": ["Never fabricate quotations"],
        },
    )
    context = ResolvedProductionContext.capture(
        prompt, recipe=BOOK_TO_TELEGRAM_POST, identity=identity
    )
    restored = ResolvedProductionContext.from_dict(context.to_dict())
    assert restored.schema_version == 3
    assert restored.identity == identity
    assert restored.recipe == BOOK_TO_TELEGRAM_POST


def test_schema_v3_requires_identity_and_recipe():
    value = {
        "schema_version": 3,
        "origin": RUNTIME_RESOLUTION,
        "captured_at": None,
        "prompt_template": {
            "template_id": "00000000-0000-0000-0000-000000000001",
            "version_id": "00000000-0000-0000-0000-000000000002",
            "key": "editorial.drafter",
            "version": 1,
            "body": "prompt",
        },
        "recipe": {
            "key": "BOOK_TO_TELEGRAM_POST",
            "version": 1,
            "stages": [{"key": "produce-post", "capability_key": "produce_post", "capability_version": 1}],
        },
    }
    with pytest.raises(ValueError, match="requires recipe and identity"):
        ResolvedProductionContext.from_dict(value)



def test_schema_v4_pins_output_contract_and_round_trips():
    from app.domain.production_context import PinnedOutputContract
    from app.domain.recipes import BOOK_TO_TELEGRAM_POST

    prompt = ResolvedPrompt(
        key="editorial.drafter",
        version=1,
        body="prompt",
        template_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    contract = PinnedOutputContract(
        contract_id="00000000-0000-0000-0000-000000000003",
        version_id="00000000-0000-0000-0000-000000000004",
        key="TELEGRAM_POST",
        version=1,
        definition={
            "artifact_kind": "POST",
            "mime_type": "text/plain",
            "content_mode": "INLINE",
            "required_metadata_fields": [],
            "max_content_chars": 100000,
        },
    )
    context = ResolvedProductionContext.capture(
        prompt, recipe=BOOK_TO_TELEGRAM_POST, output_contract=contract
    )
    restored = ResolvedProductionContext.from_dict(context.to_dict())
    assert restored.schema_version == 4
    assert restored.output_contract == contract
    assert restored.recipe == BOOK_TO_TELEGRAM_POST


def test_schema_v4_requires_output_contract():
    from app.domain.production_context import PinnedPrompt

    prompt = PinnedPrompt(
        template_id="00000000-0000-0000-0000-000000000001",
        version_id="00000000-0000-0000-0000-000000000002",
        key="editorial.drafter",
        version=1,
        body="prompt",
    )
    with pytest.raises(ValueError, match="requires pinned recipe and output contract"):
        ResolvedProductionContext(
            schema_version=4, origin=RUNTIME_RESOLUTION, captured_at=None,
            prompt_template=prompt, recipe=None, output_contract=None,
        )


def test_schema_v5_pins_policy_and_round_trips():
    from app.domain.production_context import PinnedOutputContract, PinnedPolicy
    from app.domain.recipes import BOOK_TO_TELEGRAM_POST

    prompt = ResolvedPrompt(key="editorial.drafter", version=1, body="prompt",
        template_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("00000000-0000-0000-0000-000000000002"))
    contract = PinnedOutputContract(contract_id="00000000-0000-0000-0000-000000000003",
        version_id="00000000-0000-0000-0000-000000000004", key="TELEGRAM_POST", version=1,
        definition={"artifact_kind":"POST","mime_type":"text/plain","content_mode":"INLINE",
                    "required_metadata_fields":[],"max_content_chars":100000})
    policy = PinnedPolicy(policy_id="00000000-0000-0000-0000-000000000005",
        version_id="00000000-0000-0000-0000-000000000006", key="EDITORIAL_DEFAULT", version=1,
        definition={"min_content_chars":1,"max_content_chars":100000,"required_terms":[],
                    "forbidden_terms":[],"allow_urls":True})
    context = ResolvedProductionContext.capture(prompt, recipe=BOOK_TO_TELEGRAM_POST,
        output_contract=contract, policy=policy)
    restored = ResolvedProductionContext.from_dict(context.to_dict())
    assert restored == context
    assert restored.schema_version == 5
    assert restored.policy == policy

