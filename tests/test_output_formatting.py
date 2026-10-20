import pytest

from app.application.posts import format_existing_editorial_content
from app.domain.recipes import RecipeStage, validate_recipe_stage_configuration


class FakeDrafter:
    def __init__(self, result: str = "عنوان منسق\n\nالنص الأصلي.") -> None:
        self.result = result
        self.calls = []

    async def draft(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


@pytest.mark.asyncio
async def test_formatting_is_skipped_when_no_explicit_formatting_instructions():
    drafter = FakeDrafter()
    original = "النص الأصلي كما أنتجه النموذج."

    result = await format_existing_editorial_content(
        drafter,
        title="عنوان",
        content=original,
        source_name="المصدر",
        instructions=None,
    )

    assert result == original
    assert drafter.calls == []


@pytest.mark.asyncio
async def test_explicit_formatting_uses_existing_text_and_preservation_instructions():
    drafter = FakeDrafter("عنوان منسق\n\nالنص الأصلي.")
    original = "النص الأصلي."

    result = await format_existing_editorial_content(
        drafter,
        title="عنوان",
        content=original,
        source_name="المصدر",
        instructions="نظّم الفقرات وأصلح علامات الترقيم دون تغيير النص.",
    )

    assert result == "عنوان منسق\n\nالنص الأصلي."
    assert len(drafter.calls) == 1
    call = drafter.calls[0]
    assert call["content"] == original
    assert call["title"] == "عنوان"
    assert call["source_name"] == "المصدر"
    assert "لا تضف أفكارًا" in call["system_prompt"]
    assert "نظّم الفقرات وأصلح علامات الترقيم دون تغيير النص." in call["system_prompt"]


@pytest.mark.asyncio
async def test_empty_formatted_result_fails_instead_of_replacing_content_with_empty_text():
    drafter = FakeDrafter("  ")

    with pytest.raises(ValueError, match="formatter returned empty content"):
        await format_existing_editorial_content(
            drafter,
            title="عنوان",
            content="النص الأصلي.",
            source_name="المصدر",
            instructions="نسّق النص.",
        )


def test_recipe_stage_accepts_optional_formatting_instructions():
    stage = RecipeStage(
        key="produce-text",
        capability_key="produce_text_artifact",
        capability_version=1,
        configuration={"formatting_instructions": "نظّم الفقرات مع الحفاظ على النص."},
    )

    validate_recipe_stage_configuration(stage)


def test_recipe_stage_rejects_blank_formatting_instructions():
    stage = RecipeStage(
        key="produce-text",
        capability_key="produce_text_artifact",
        capability_version=1,
        configuration={"formatting_instructions": "  "},
    )

    with pytest.raises(ValueError, match="formatting_instructions"):
        validate_recipe_stage_configuration(stage)
