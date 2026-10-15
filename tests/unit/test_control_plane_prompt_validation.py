import pytest

from app.application.control_plane import validate_prompt_template_body


def test_discovery_prompt_template_accepts_required_variables() -> None:
    validate_prompt_template_body(
        "knowledge.book_map.section",
        "نافذة {{page_start}}-{{page_end}} وعدد صفحاتها {{window_page_count}}",
    )


def test_discovery_prompt_template_rejects_missing_required_variable() -> None:
    with pytest.raises(ValueError, match="missing required variables"):
        validate_prompt_template_body(
            "knowledge.book_map.section",
            "نافذة {{page_start}}-{{page_end}}",
        )


def test_discovery_prompt_template_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unsupported variables"):
        validate_prompt_template_body(
            "knowledge.material_discovery.context",
            (
                "مصدر {{source_name}}؛ موضوع {{topic_title}}؛ وصف {{topic_description}}؛ "
                "صفحات {{page_start}}-{{page_end}}؛ متغير {{secret}}"
            ),
        )
