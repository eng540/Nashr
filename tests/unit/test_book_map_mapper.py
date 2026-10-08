from types import SimpleNamespace
from uuid import uuid4

from app.adapters.extraction.gemini import GeminiBookMapper, GeminiOperationError
from app.domain.sources import Source


def test_book_map_page_ranges_are_contiguous_and_bounded() -> None:
    assert GeminiBookMapper._page_ranges(150, 64) == [
        (1, 64),
        (65, 128),
        (129, 150),
    ]


def test_book_map_section_normalizes_relative_provenance_to_absolute_pages() -> None:
    items = [
        type("Topic", (), {
            "page_start": 1,
            "page_end": 4,
            "model_copy": lambda self, update: type("Topic", (), {
                "page_start": update["page_start"],
                "page_end": update["page_end"],
            })(),
        })(),
    ]

    normalized = GeminiBookMapper._normalize_section_topics(items, 65, 128)

    assert normalized[0].page_start == 65
    assert normalized[0].page_end == 68


def test_book_map_section_rejects_absolute_pages_as_relative_provenance() -> None:
    item = type("Topic", (), {
        "page_start": 129,
        "page_end": 158,
    })()

    try:
        GeminiBookMapper._normalize_section_topics([item], 65, 128)
    except GeminiOperationError as exc:
        assert exc.code == "GEMINI_PROVENANCE_UNAVAILABLE"
    else:
        raise AssertionError("Absolute-looking pages must not be accepted as relative provenance.")


def test_book_map_section_adapts_after_context_limit() -> None:
    mapper = object.__new__(GeminiBookMapper)
    source = SimpleNamespace(id=uuid4())
    calls: list[tuple[int, int]] = []

    def fake_map_section(source, reader, page_start, page_end, section_index):
        calls.append((page_start, page_end))
        if page_end - page_start + 1 > 1:
            raise GeminiOperationError(
                "GEMINI_INVALID_ARGUMENT",
                "bounded request failed",
                False,
                ValueError("input token count exceeds the maximum number of tokens allowed"),
            )
        return f"map:{page_start}-{page_end}"

    mapper._map_section = fake_map_section
    result = mapper._map_section_adaptive(source, object(), 1, 4, section_index=1)

    assert result == ["map:1-1", "map:2-2", "map:3-3", "map:4-4"]
    assert calls == [(1, 4), (1, 2), (1, 1), (2, 2), (3, 4), (3, 3), (4, 4)]


def test_book_map_merge_is_hierarchical() -> None:
    mapper = object.__new__(GeminiBookMapper)
    source = SimpleNamespace(id=uuid4())
    maps = []
    for index in range(13):
        maps.append(
            type("Map", (), {
                "title": f"Map {index}",
                "description": "",
                "topics": [],
            })()
        )

    calls: list[int] = []

    def fake_merge(source, batch, page_count, section_count, round_index, batch_index):
        calls.append(len(batch))
        return maps[0]

    mapper._merge_maps_batch = fake_merge
    result = mapper._merge_maps_hierarchical(source, maps, 1113, 13)

    assert result is maps[0]
    assert calls == [6, 6, 1, 3]

def test_book_map_usage_logging_uses_source_id_without_source_scope() -> None:
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=123,
            candidates_token_count=7,
            total_token_count=130,
            cached_content_token_count=0,
        )
    )
    source_id = uuid4()

    GeminiBookMapper._log_usage(response, source_id, "BUILDING_BOOK_MAP_SECTION")
