from app.adapters.extraction.gemini import GeminiBookMap, GeminiIdeas, GeminiTopic


def test_book_map_schema_does_not_limit_topic_count_or_taxonomy() -> None:
    payload = GeminiBookMap(
        title="Book",
        description="Desc",
        topics=[
            GeminiTopic(position=i, title=f"Topic {i}", description="d", page_start=i, page_end=i)
            for i in range(1, 9)
        ],
    )
    assert len(payload.topics) == 8


def test_material_schema_allows_open_ended_kind_and_zero_results() -> None:
    payload = GeminiIdeas(ideas=[])
    assert payload.ideas == []
