from typing import Protocol


class ObjectStorage(Protocol):
    async def put(self, *, key: str, content: bytes, content_type: str) -> str:
        """Persist private media bytes under a validated key and return an s3:// URI."""

    async def presign_get(self, storage_uri: str, *, expires_seconds: int = 300) -> str:
        """Return a short-lived private media URL for review."""
