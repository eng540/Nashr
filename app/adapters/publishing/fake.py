from app.domain.publications import IPublisher, PublishResult


class FakePublisher(IPublisher):
    """Publish deterministically without an external service."""

    async def publish(
        self, *, destination: str, content: str, media: bytes | None = None, media_mime_type: str | None = None
    ) -> PublishResult:
        """Return a deterministic external message identifier for text or media."""
        return PublishResult(external_id="test_msg_999")
