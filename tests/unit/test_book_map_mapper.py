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
