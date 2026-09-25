from app.adapters.extraction.gemini import GeminiExtractor


def test_extraction_prompt_excludes_non_content_sections_and_targets_core_ideas() -> None:
    """Verify the extraction prompt encodes the editorial extraction boundaries."""
    prompt = GeminiExtractor.SYSTEM_PROMPT
    assert "الفهارس" in prompt
    assert "المراجع" in prompt
    assert "مقدمات التحقيق" in prompt
    assert "الدرر الفكرية" in prompt
    assert "المواقف العملية المباشرة" in prompt
