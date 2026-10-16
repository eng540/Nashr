from collections.abc import Sequence

from app.domain.editorial import EditorialSourceMaterial, IEditorialDrafter


class FakeEditorialDrafter(IEditorialDrafter):
    """Create deterministic editorial content for tests."""

    async def draft(
        self,
        *,
        title: str,
        content: str,
        source_name: str,
        pdf_slice: bytes | None = None,
        system_prompt: str | None = None,
    ) -> str:
        return f"**{title}**\n\n{content}\n\n📚 {source_name}\n#اختبار"

    async def draft_sources(
        self,
        *,
        theme: str,
        sources: Sequence[EditorialSourceMaterial],
        system_prompt: str,
    ) -> str:
        if not theme.strip() or len(sources) < 2:
            raise ValueError("Thematic composition requires a theme and at least two sources.")
        if not system_prompt.strip():
            raise ValueError("Resolved editorial prompt is required.")
        return "\n\n".join(
            f"[{index}] {source.title}\n{source.content}\n📚 {source.source_name}"
            for index, source in enumerate(sources, start=1)
        )
