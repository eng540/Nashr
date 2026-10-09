from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.domain.posts import Post
from app.infrastructure.database.models import ArtifactModel, PostModel


def post_to_artifact(
    post: Post,
    *,
    production_job_id: UUID | None = None,
    resolved_context: dict | None = None,
) -> Artifact:
    """Expose a Post through the generic Artifact boundary without owning editorial state."""
    return Artifact(
        id=post.id,
        source_knowledge_unit_id=post.knowledge_unit_id,
        kind=ArtifactKind.POST,
        content=post.content,
        status=ArtifactStatus.AVAILABLE.value,
        created_at=post.created_at,
        updated_at=post.updated_at,
        post_id=post.id,
        editorial_status=post.status.value,
        production_job_id=production_job_id,
        resolved_context=resolved_context,
    )


async def ensure_post_artifact(
    session: AsyncSession,
    post: Post,
    *,
    production_job_id: UUID | None,
    resolved_context: dict | None,
) -> Artifact:
    """Persist the durable Artifact reference for a Post, without rewriting prior provenance."""
    existing = (
        await session.execute(select(ArtifactModel).where(ArtifactModel.id == post.id))
    ).scalar_one_or_none()
    if existing is None:
        await session.execute(
            insert(ArtifactModel)
            .values(
                id=post.id,
                source_knowledge_unit_id=post.knowledge_unit_id,
                kind=ArtifactKind.POST.value,
                status=ArtifactStatus.AVAILABLE.value,
                post_id=post.id,
                production_job_id=production_job_id,
                resolved_context=resolved_context,
                created_at=post.created_at,
                updated_at=post.updated_at,
                artifact_metadata={},
            )
            .on_conflict_do_nothing(index_elements=[ArtifactModel.id])
        )
        await session.commit()
    artifact = await load_artifact(session, post.id)
    if artifact is None:
        raise RuntimeError("Artifact persistence did not produce a readable record.")
    return artifact


async def load_artifact(session: AsyncSession, artifact_id: UUID) -> Artifact | None:
    result = await session.execute(
        select(ArtifactModel).where(ArtifactModel.id == artifact_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    post: PostModel | None = None
    if row.kind == ArtifactKind.POST.value and row.post_id is not None:
        post = (
            await session.execute(select(PostModel).where(PostModel.id == row.post_id))
        ).scalar_one_or_none()

    return Artifact(
        id=row.id,
        source_knowledge_unit_id=row.source_knowledge_unit_id,
        kind=ArtifactKind(row.kind),
        content=post.content if post is not None else row.content,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        storage_uri=row.storage_uri,
        mime_type=row.mime_type,
        post_id=row.post_id,
        editorial_status=post.status if post is not None else None,
        production_job_id=row.production_job_id,
        output_contract_key=row.output_contract_key,
        output_contract_version=row.output_contract_version,
        resolved_context=row.resolved_context,
        metadata=row.artifact_metadata,
    )


async def load_post_model_to_artifact(session: AsyncSession, post_id: UUID) -> Artifact:
    """Compatibility helper: expose a persisted Post row through the Artifact boundary."""
    result = await session.execute(select(PostModel).where(PostModel.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise ValueError("Post not found for Artifact conversion.")
    return post_model_to_artifact(post)


def post_model_to_artifact(post: PostModel) -> Artifact:
    """Expose a persisted Post while keeping its editorial state distinct from Artifact state."""
    return Artifact(
        id=post.id,
        source_knowledge_unit_id=post.knowledge_unit_id,
        kind=ArtifactKind.POST,
        content=post.content,
        status=ArtifactStatus.AVAILABLE.value,
        created_at=post.created_at,
        updated_at=post.updated_at,
        post_id=post.id,
        editorial_status=post.status,
    )
