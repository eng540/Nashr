from pathlib import Path
from uuid import uuid4


class LocalFileStorage:
    """Store uploaded files under a configured local directory."""

    def __init__(self, root: str) -> None:
        """Initialize local storage with its root directory."""
        self.root = Path(root)

    async def save(self, filename: str, content: bytes, prefix: str | None = None) -> str:
        """Save file bytes under an ASCII-safe unique name while preserving the original filename in the source record."""
        self.root.mkdir(parents=True, exist_ok=True)
        extension = Path(filename).suffix.lower() or ".pdf"
        unique_prefix = prefix or str(uuid4())
        unique_name = f"{unique_prefix}_source{extension}"
        path = self.root / unique_name
        path.write_bytes(content)
        return str(path)
