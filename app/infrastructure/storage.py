from pathlib import Path

class LocalFileStorage:
    """Store uploaded files under a configured local directory."""

    def __init__(self, root: str) -> None:
        """Initialize local storage with its root directory."""
        self.root = Path(root)

    async def save(self, filename: str, content: bytes) -> str:
        """Save file bytes and return the storage path."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / filename
        path.write_bytes(content)
        return str(path)
