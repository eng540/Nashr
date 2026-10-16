from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.application.artifacts import persist_generic_artifact
from app.application.control_plane import ControlPlaneResolver, EDITORIAL_PROMPT_KEY
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.domain.editorial import EditorialSourceMaterial
from app.domain.output_contracts import OutputContractDefinition
from app.domain.production_context import PinnedOutputContract
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


async def persist_thematic_draft(
    session: AsyncSession,
    result: ThematicCompositionResult,
    *,
    resolved_context: dict,
    production_job_id: UUID | None = None,
) -> Artifact:
    """Persist a multi-source draft through Nashr's existing Artifact boundary.

    The first source is only the required legacy/relational anchor. The complete
    source set is retained in Artifact metadata and is never collapsed to that anchor.
    The output remains a DRAFT for the existing human review flow.
    """
    if not result.sources or len(result.sources) < 2:
        raise ValueError("A thematic Artifact requires at least two provenance sources.")
    source_ids = [source.knowledge_unit_id for source in result.sources]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Thematic Artifact provenance contains duplicate source IDs.")
    if not isinstance(resolved_context, dict) or "output_contract" not in resolved_context:
        raise ValueError("Thematic Artifact persistence requires a pinned output contract.")

    pinned = PinnedOutputContract.from_dict(resolved_context["output_contract"])
    contract = OutputContractDefinition.from_dict(pinned.definition)
    if (
        contract.artifact_kind != ArtifactKind.TEXT.value
        or contract.content_mode != "INLINE"
        or contract.mime_type != "text/plain"
    ):
        raise ValueError("Thematic composition requires a pinned inline TEXT contract with text/plain MIME type.")
    if not result.content.strip():
        raise ValueError("Thematic Artifact content cannot be empty.")

    metadata = {
        "title": result.theme,
        "theme": result.theme,
        "composition_mode": "MULTI_SOURCE_THEMATIC",
        "source_knowledge_unit_ids": source_ids,
        "sources": [
            {
                "knowledge_unit_id": source.knowledge_unit_id,
                "title": source.title,
                "source_name": source.source_name,
                "source_reference": source.source_reference,
            }
            for source in result.sources
        ],
    }
    artifact = Artifact(
        id=uuid4(),
        source_knowledge_unit_id=UUID(result.sources[0].knowledge_unit_id),
        kind=ArtifactKind.TEXT,
        content=result.content,
        status=ArtifactStatus.AVAILABLE.value,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        mime_type=contract.mime_type,
        production_job_id=production_job_id,
        output_contract_key=pinned.key,
        output_contract_version=pinned.version,
        resolved_context=dict(resolved_context),
        metadata=metadata,
    )
    return await persist_generic_artifact(
        session,
        artifact,
        resolved_context=dict(resolved_context),
    )
