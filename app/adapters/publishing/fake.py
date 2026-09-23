from app.domain.publications import IPublisher, PublishResult


class FakePublisher(IPublisher):
    """Publish deterministically without an external service."""

    async def publish(self, *, destination: str, content: str) -> PublishResult:
        """Return a deterministic external message identifier."""
        return PublishResult(external_id="test_msg_999")
