from typing import Protocol


class IEditorialDrafter(Protocol):
    """Define the port for turning a knowledge unit into publication-ready copy."""

    async def draft(self, *, title: str, content: str, source_name: str) -> str:
        """Create a complete Telegram post in Markdown."""
