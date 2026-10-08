from typing import Protocol


class IEditorialDrafter(Protocol):
    """Define the port for turning a knowledge unit into publication-ready copy."""

    async def draft(
        self,
        *,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Create a Telegram post, optionally grounded by a visual PDF slice."""
