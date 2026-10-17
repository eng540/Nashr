import pytest

from app.adapters.publishing.telegram import TelegramPublisher


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "result": {"message_id": 4321}}


class FakeAsyncClient:
    calls = []

    def __init__(self, *, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


@pytest.mark.asyncio
async def test_telegram_publisher_sends_approved_image_as_photo_caption_without_network(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr("app.adapters.publishing.telegram.httpx.AsyncClient", FakeAsyncClient)
    publisher = TelegramPublisher(token="test-token")
    result = await publisher.publish(
        destination="@test-channel",
        content="نص معتمد",
        media=b"png-image-bytes",
        media_mime_type="image/png",
    )
    assert result.external_id == "4321"
    url, request = FakeAsyncClient.calls[0]
    assert url.endswith("/sendPhoto")
    assert request["data"] == {"chat_id": "@test-channel", "caption": "نص معتمد", "parse_mode": "HTML"}
    assert request["files"]["photo"] == ("nashr-card.png", b"png-image-bytes", "image/png")


@pytest.mark.asyncio
async def test_telegram_publisher_keeps_legacy_text_send_message_path(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr("app.adapters.publishing.telegram.httpx.AsyncClient", FakeAsyncClient)
    publisher = TelegramPublisher(token="test-token")
    result = await publisher.publish(destination="@test-channel", content="نص فقط")
    assert result.external_id == "4321"
    url, request = FakeAsyncClient.calls[0]
    assert url.endswith("/sendMessage")
    assert request["json"] == {"chat_id": "@test-channel", "text": "نص فقط", "parse_mode": "HTML"}
