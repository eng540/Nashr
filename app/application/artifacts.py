from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.artifacts import Artifact, ArtifactKind
from app.domain.posts import Post
from app.infrastructure.database.models import PostModel


def post_to_artifact(post: Post) -> Artifact:
    """Expose the current Post as the first concrete Artifact representation."""
    return Artifact(
        id=post.id,
        source_knowledge_unit_id=post.knowledge_unit_id,
        kind=ArtifactKind.POST,
        content=post.content,
        status=post.status.value,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


async def load_post_model_to_artifact(session: AsyncSession, post_id: UUID) -> Artifact:
    """Load the persisted Post only at the compatibility edge and expose it as Artifact."""
    result = await session.execute(select(PostModel).where(PostModel.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise ValueError("Post not found for Artifact conversion.")
    return post_model_to_artifact(post)


def post_model_to_artifact(post: PostModel) -> Artifact:
    """Expose a persisted Post row through the generic Artifact boundary."""
    return Artifact(
        id=post.id,
        source_knowledge_unit_id=post.knowledge_unit_id,
        kind=ArtifactKind.POST,
        content=post.content,
        status=post.status,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )
