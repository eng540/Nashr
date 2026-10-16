from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.application.control_plane import ControlPlaneResolver, EDITORIAL_PROMPT_KEY
from app.domain.editorial import EditorialSourceMaterial
from app.infrastructure.database.models import KnowledgeUnitModel


@dataclass(frozen=True)
class ThematicCompositionResult:
    """A generated draft plus the exact source set used to create it."""

    theme: str
    content: str
    sources: tuple[EditorialSourceMaterial, ...]


def validate_thematic_selection(theme: str, knowledge_unit_ids: list[UUID]) -> None:
    if not theme.strip():
        raise ValueError("Theme must not be empty.")
    if len(knowledge_unit_ids) < 2:
        raise ValueError("Select at least two knowledge units for thematic composition.")
    if len(set(knowledge_unit_ids)) != len(knowledge_unit_ids):
        raise ValueError("Selected knowledge units must not contain duplicates.")


class ComposeThematicDraft:
    """Compose from explicit Knowledge Units using the published editorial prompt."""

    def __init__(
        self,
        drafter: GeminiEditorialDrafter | None = None,
        resolver: ControlPlaneResolver | None = None,
    ) -> None:
        self.drafter = drafter or GeminiEditorialDrafter()
        self.resolver = resolver or ControlPlaneResolver()

    async def execute(
        self,
        session: AsyncSession,
        *,
        theme: str,
        knowledge_unit_ids: list[UUID],
        system_prompt: str | None = None,
    ) -> ThematicCompositionResult:
        validate_thematic_selection(theme, knowledge_unit_ids)
        result = await session.execute(
            select(KnowledgeUnitModel)
            .options(selectinload(KnowledgeUnitModel.source))
            .where(KnowledgeUnitModel.id.in_(knowledge_unit_ids))
        )
        units_by_id = {unit.id: unit for unit in result.scalars().all()}
        missing = [str(unit_id) for unit_id in knowledge_unit_ids if unit_id not in units_by_id]
        if missing:
            raise ValueError("Selected knowledge units were not found: " + ", ".join(missing))

        materials = []
        for unit_id in knowledge_unit_ids:
            unit = units_by_id[unit_id]
            source = unit.source
            source_name = (
                (source.book_title or source.filename) if source is not None else "المصدر غير المعروف"
            )
            materials.append(
                EditorialSourceMaterial(
                    knowledge_unit_id=str(unit.id),
                    title=unit.title,
                    content=(unit.original_text or unit.content),
                    source_name=source_name,
                    source_reference=unit.source_reference,
                )
            )
        prompt = system_prompt
        if prompt is None:
            prompt = (await self.resolver.resolve_prompt(session, EDITORIAL_PROMPT_KEY)).body
        if not prompt or not prompt.strip():
            raise LookupError("Published editorial prompt is empty.")
        content = await self.drafter.draft_sources(
            theme=theme,
            sources=materials,
            system_prompt=prompt,
        )
        if not content.strip():
            raise ValueError("Thematic drafter returned empty content.")
        return ThematicCompositionResult(theme=theme.strip(), content=content, sources=tuple(materials))
