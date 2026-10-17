import pytest

from app.adapters.publishing.telegram import telegram_html_content


def test_plain_text_is_escaped_for_telegram_html_mode() -> None:
    assert telegram_html_content("A < B & C") == "A &lt; B &amp; C"


def test_supported_rich_text_tags_are_preserved() -> None:
    assert telegram_html_content("<b>عنوان</b>\n<blockquote>اقتباس</blockquote>") == (
        "<b>عنوان</b>\n<blockquote>اقتباس</blockquote>"
    )


def test_rich_text_escapes_text_nodes_and_link_attributes() -> None:
    assert telegram_html_content('<a href="https://example.com/?a=1&b=2">A & B</a>') == (
        '<a href="https://example.com/?a=1&amp;b=2">A &amp; B</a>'
    )


def test_unbalanced_rich_text_is_rejected() -> None:
    with pytest.raises(ValueError, match="unclosed|Unbalanced"):
        telegram_html_content("<b>عنوان")


def test_unsupported_rich_text_tags_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported Telegram HTML tag"):
        telegram_html_content("<b>عنوان</b><customtag>نص</customtag>")


def test_message_limit_counts_visible_text_not_markup() -> None:
    assert len(telegram_html_content("<b>" + "x" * 4096 + "</b>")) > 4096
    with pytest.raises(ValueError, match="4096"):
        telegram_html_content("<b>" + "x" * 4097 + "</b>")


def test_caption_limit_can_be_set_for_photo_publications():
    assert len(telegram_html_content("x" * 1024, max_visible_characters=1024)) == 1024
    with pytest.raises(ValueError, match="1024"):
        telegram_html_content("x" * 1025, max_visible_characters=1024)
