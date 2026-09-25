from app.domain.editorial import IEditorialDrafter


class FakeEditorialDrafter(IEditorialDrafter):
    """Create deterministic editorial content for tests."""

    async def draft(self, *, title: str, content: str, source_name: str) -> str:
        """Return deterministic Markdown-like Telegram content."""
        return f"**{title}**\\n\\n{content}\\n\\n📚 {source_name}\\n#اختبار"
