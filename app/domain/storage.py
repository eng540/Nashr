from typing import Protocol


class ObjectStorage(Protocol):
    async def save(
        self,
        filename: str,
        content: bytes,
        prefix: str | None = None,
        mime_type: str | None = None,
    ) -> str:
        """Persist bytes and return a provider-neutral storage URI."""

    async def download_url(self, storage_uri: str, expires_seconds: int = 900) -> str:
        """Return a short-lived URL for reviewing a stored artifact."""
