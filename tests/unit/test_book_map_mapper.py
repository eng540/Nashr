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

    def fake_map_section(source, page_start, page_end, section_index):
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
    result = mapper._map_section_adaptive(source, 1, 4, section_index=1)

    assert result == ["map:1-1", "map:2-2", "map:3-3", "map:4-4"]
    assert calls == [(1, 4), (1, 2), (1, 1), (2, 2), (3, 4), (3, 3), (4, 4)]
