from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class EditorialSourceMaterial:
    """One explicitly selected, traceable source for multi-material composition."""

    knowledge_unit_id: str
    title: str
    content: str
    source_name: str
    source_reference: str | None = None


class IEditorialDrafter(Protocol):
    """Define the port for turning source material into publication-ready copy."""

    async def draft(
        self,
        *,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Create a draft from one source material."""

    async def draft_sources(
        self,
        *,
        theme: str,
        sources: Sequence[EditorialSourceMaterial],
        system_prompt: str,
    ) -> str:
        """Create a traceable synthesis from multiple explicitly selected sources."""
