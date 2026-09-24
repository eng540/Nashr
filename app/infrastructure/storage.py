from pathlib import Path
from uuid import uuid4


class LocalFileStorage:
    """Store uploaded files under a configured local directory."""

    def __init__(self, root: str) -> None:
        """Initialize local storage with its root directory."""
        self.root = Path(root)

    async def save(self, filename: str, content: bytes, prefix: str | None = None) -> str:
        """Save file bytes under a unique ASCII-safe storage filename."""
        self.root.mkdir(parents=True, exist_ok=True)
        extension = Path(filename).suffix.lower()
        unique_name = f"{prefix}.pdf" if prefix else f"{uuid4()}.pdf"
        if extension == ".pdf":
            path = self.root / unique_name
        else:
            path = self.root / f"{Path(unique_name).stem}{extension}"
        path.write_bytes(content)
        return str(path)
