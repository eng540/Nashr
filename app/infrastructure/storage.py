from pathlib import Path
from uuid import uuid4


class LocalFileStorage:
    """Store uploaded files under a configured local directory."""

    def __init__(self, root: str) -> None:
        """Initialize local storage with its root directory."""
        self.root = Path(root)

    async def save(self, filename: str, content: bytes, prefix: str | None = None) -> str:
        """Save file bytes using an optional source identifier to prevent collisions."""
        self.root.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name
        unique_name = f"{prefix}_{safe_name}" if prefix else f"{uuid4()}_{safe_name}"
        path = self.root / unique_name
        path.write_bytes(content)
        return str(path)
