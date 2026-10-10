import logging

from app.main import configure_logging


def test_httpx_info_logs_are_disabled_to_protect_telegram_bot_token_paths(monkeypatch):
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    original_root_level = root.level
    original_httpx_level = httpx_logger.level
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    try:
        configure_logging()
        assert httpx_logger.level >= logging.WARNING
    finally:
        root.setLevel(original_root_level)
        httpx_logger.setLevel(original_httpx_level)
