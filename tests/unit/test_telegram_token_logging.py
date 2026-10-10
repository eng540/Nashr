import logging

from app.main import configure_logging


def test_httpx_info_logs_do_not_emit_telegram_bot_token_paths(monkeypatch, caplog):
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    app_logger = logging.getLogger("app")
    original_root_level = root.level
    original_httpx_level = httpx_logger.level
    original_httpcore_level = httpcore_logger.level
    original_app_level = app_logger.level
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    try:
        configure_logging()
        assert httpx_logger.level >= logging.WARNING
        assert httpcore_logger.level >= logging.WARNING
        with caplog.at_level(logging.DEBUG):
            httpx_logger.info(
                "HTTP Request: POST https://api.telegram.org/botTEST_TOKEN_MUST_NOT_LEAK/sendMessage"
            )
            httpcore_logger.debug("send_request_headers.started request=POST path=/botTEST_TOKEN_MUST_NOT_LEAK/sendMessage")
        assert "TEST_TOKEN_MUST_NOT_LEAK" not in caplog.text
        assert "HTTP Request: POST" not in caplog.text
        assert "send_request_headers.started" not in caplog.text
    finally:
        root.setLevel(original_root_level)
        httpx_logger.setLevel(original_httpx_level)
        httpcore_logger.setLevel(original_httpcore_level)
        app_logger.setLevel(original_app_level)
