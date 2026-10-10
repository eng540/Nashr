from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.application.artifacts import ensure_post_artifact, post_model_to_artifact, post_to_artifact
from app.domain.production_context import PinnedPolicy
from app.domain.artifacts import ArtifactKind, ArtifactStatus
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
    assert artifact.status == ArtifactStatus.AVAILABLE.value
    assert artifact.editorial_status == PostStatus.APPROVED.value
    assert artifact.post_id == post.id


def test_persisted_post_is_exposed_through_same_artifact_boundary():
    now = datetime.now(timezone.utc)
    post = SimpleNamespace(
        id=uuid4(),
        knowledge_unit_id=uuid4(),
        content="نص منشور محفوظ",
        status=PostStatus.APPROVED.value,
        created_at=now,
        updated_at=now,
    )

    artifact = post_model_to_artifact(post)

    assert artifact.id == post.id
    assert artifact.source_knowledge_unit_id == post.knowledge_unit_id
    assert artifact.kind is ArtifactKind.POST
    assert artifact.content == post.content
    assert artifact.status == ArtifactStatus.AVAILABLE.value
    assert artifact.editorial_status == PostStatus.APPROVED.value
    assert artifact.post_id == post.id

def test_artifact_contract_represents_image_and_video_storage_without_post_fields():
    from app.domain.artifacts import Artifact

    now = datetime.now(timezone.utc)
    for kind, mime_type, uri in (
        (ArtifactKind.IMAGE, "image/png", "s3://nashr/artifacts/image.png"),
        (ArtifactKind.VIDEO, "video/mp4", "s3://nashr/artifacts/video.mp4"),
    ):
        artifact = Artifact(
            id=uuid4(),
            source_knowledge_unit_id=uuid4(),
            kind=kind,
            content=None,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            storage_uri=uri,
            mime_type=mime_type,
        )
        assert artifact.kind is kind
        assert artifact.storage_uri == uri
        assert artifact.post_id is None
        assert artifact.editorial_status is None


@pytest.mark.asyncio
async def test_artifact_persistence_rejects_content_violating_pinned_policy():
    now = datetime.now(timezone.utc)
    post = Post(
        id=uuid4(), knowledge_unit_id=uuid4(), content="This includes a blocked term",
        status=PostStatus.DRAFT, created_at=now, updated_at=now,
        reviewed_at=None, review_note=None,
    )
    policy = PinnedPolicy(
        policy_id="00000000-0000-0000-0000-000000000021",
        version_id="00000000-0000-0000-0000-000000000022",
        key="TEST_POLICY", version=1,
        definition={
            "min_content_chars": 1, "max_content_chars": 1000,
            "required_terms": [], "forbidden_terms": ["blocked"], "allow_urls": True,
        },
    )
    with pytest.raises(ValueError, match="violates pinned production policy"):
        await ensure_post_artifact(
            None, post, production_job_id=None, resolved_context={"policy": policy.to_dict()}
        )
