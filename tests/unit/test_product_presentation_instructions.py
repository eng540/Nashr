import pytest

from app.application.recipe_engine import ProductionExecutionContext, _stage_system_prompt
from app.domain.products import ProductionProductDefinition


def test_product_presentation_instructions_are_versioned_in_product_definition() -> None:
    definition = ProductionProductDefinition.from_dict(
        {
            "recipe_key": "BOOK_TO_TEXT_ARTIFACT",
            "output_contract_key": "TEXT_ARTIFACT",
            "policy_key": "ARABIC_LITERATURE_POLICY",
            "audience": "Readers",
            "experience": "A readable literary text",
            "presentation_instructions": "Use short paragraphs with one blank line between them.",
        }
    )
    serialized = definition.to_dict()
    assert serialized["presentation_instructions"] == "Use short paragraphs with one blank line between them."
    assert ProductionProductDefinition.from_dict(serialized) == definition


def test_product_presentation_instructions_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="presentation_instructions must be a string"):
        ProductionProductDefinition.from_dict(
            {
                "recipe_key": "BOOK_TO_TEXT_ARTIFACT",
                "output_contract_key": "TEXT_ARTIFACT",
                "policy_key": "ARABIC_LITERATURE_POLICY",
                "audience": "Readers",
                "experience": "A readable literary text",
                "presentation_instructions": ["not", "a", "string"],
            }
        )

    with pytest.raises(ValueError, match="cannot exceed 12000 characters"):
        ProductionProductDefinition(
            recipe_key="BOOK_TO_TEXT_ARTIFACT",
            output_contract_key="TEXT_ARTIFACT",
            policy_key="ARABIC_LITERATURE_POLICY",
            audience="Readers",
            experience="A readable literary text",
            presentation_instructions="x" * 12001,
        )


def test_text_stage_system_prompt_includes_pinned_product_presentation_instructions() -> None:
    context = ProductionExecutionContext(
        session=None,  # type: ignore[arg-type]
        inputs={},
        configuration={"editorial_prompt": {"body": "BASE EDITORIAL PROMPT"}},
        resolved_context={
            "product": {
                "definition": {
                    "presentation_instructions": "Keep paragraphs breathable and preserve poetic line breaks."
                }
            }
        },
        stage_configuration={"style_instructions": "Recipe-level instructions"},
    )
    prompt = _stage_system_prompt(context, "produce_text_artifact")
    assert prompt.index("Recipe-level instructions") < prompt.index("Keep paragraphs breathable")
    assert "preserve poetic line breaks" in prompt
