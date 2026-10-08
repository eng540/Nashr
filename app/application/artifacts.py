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
