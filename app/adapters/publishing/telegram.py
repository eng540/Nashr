import os

import httpx

from app.domain.publications import IPublisher, PublishResult


class TelegramPublisher(IPublisher):
    """Publish Telegram messages through the Bot API."""

    def __init__(self, token: str | None = None, timeout: float = 30.0) -> None:
        """Initialize the Telegram Bot API client."""
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.timeout = timeout
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required.")

    async def publish(self, *, destination: str, content: str) -> PublishResult:
        """Send a message to Telegram and return its message identifier."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json={"chat_id": destination, "text": content})
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok") or "result" not in payload or "message_id" not in payload["result"]:
            raise RuntimeError("Telegram returned an invalid publish response.")
        return PublishResult(external_id=str(payload["result"]["message_id"]))
