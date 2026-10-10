import logging

from app.main import configure_logging


def test_httpx_info_logs_do_not_emit_telegram_bot_token_paths(monkeypatch, caplog):
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    app_logger = logging.getLogger("app")
    original_root_level = root.level
    original_httpx_level = httpx_logger.level
    original_app_level = app_logger.level
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    try:
        configure_logging()
        assert httpx_logger.level >= logging.WARNING
        with caplog.at_level(logging.DEBUG):
            httpx_logger.info(
                "HTTP Request: POST https://api.telegram.org/botTEST_TOKEN_MUST_NOT_LEAK/sendMessage"
            )
        assert "TEST_TOKEN_MUST_NOT_LEAK" not in caplog.text
        assert "HTTP Request: POST" not in caplog.text
    finally:
        root.setLevel(original_root_level)
        httpx_logger.setLevel(original_httpx_level)
        app_logger.setLevel(original_app_level)
