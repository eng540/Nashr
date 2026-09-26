from uuid import uuid4

from app.domain.book_map import BookMap, BookTopic


def test_book_map_allows_empty_topics() -> None:
    source_id = uuid4()
    book_map = BookMap(source_id, "Book", "Description", [])
    assert book_map.topics == []


def test_book_topic_preserves_open_ended_structure() -> None:
    source_id = uuid4()
    topic = BookTopic.create(source_id, 1, "مفارقات", "موضوع غير موجود في أي قائمة مغلقة.")
    assert topic.title == "مفارقات"
    assert topic.source_reference is None
