from datetime import datetime, timezone
from uuid import uuid4

from app.application.artifacts import post_to_artifact
from app.domain.artifacts import ArtifactKind
from app.domain.posts import Post, PostStatus


def test_post_is_exposed_through_generic_artifact_boundary():
    now = datetime.now(timezone.utc)
    post = Post(
        id=uuid4(),
        knowledge_unit_id=uuid4(),
        content="نص الاختبار",
        status=PostStatus.APPROVED,
        created_at=now,
        updated_at=now,
        reviewed_at=now,
        review_note="approved",
    )

    artifact = post_to_artifact(post)

    assert artifact.id == post.id
    assert artifact.source_knowledge_unit_id == post.knowledge_unit_id
    assert artifact.kind is ArtifactKind.POST
    assert artifact.content == post.content
    assert artifact.status == PostStatus.APPROVED.value
