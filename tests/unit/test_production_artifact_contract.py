from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactStatus,
    validate_production_artifact,
)


NOW = datetime.now(timezone.utc)


def _artifact(kind: ArtifactKind, job_id, source_id, **overrides) -> Artifact:
    values = {
        "id": uuid4(),
        "source_knowledge_unit_id": source_id,
        "kind": kind,
        "content": "valid text" if kind in {ArtifactKind.POST, ArtifactKind.TEXT} else None,
        "status": ArtifactStatus.AVAILABLE.value,
        "created_at": NOW,
        "updated_at": NOW,
        "storage_uri": None if kind in {ArtifactKind.POST, ArtifactKind.TEXT} else "s3://private/artifact",
        "mime_type": "text/plain" if kind in {ArtifactKind.POST, ArtifactKind.TEXT} else {
            ArtifactKind.IMAGE: "image/png",
            ArtifactKind.VIDEO: "video/mp4",
            ArtifactKind.AUDIO: "audio/wav",
        }[kind],
        "post_id": uuid4() if kind == ArtifactKind.POST else None,
        "production_job_id": job_id,
    }
    values.update(overrides)
    return Artifact(**values)


@pytest.mark.parametrize("kind", list(ArtifactKind))
def test_shared_artifact_contract_accepts_valid_result_for_each_kind(kind):
    job_id, source_id = uuid4(), uuid4()
    validate_production_artifact(
        _artifact(kind, job_id, source_id),
        expected_job_id=job_id,
        expected_source_knowledge_unit_id=source_id,
    )


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"status": ArtifactStatus.FAILED.value}, "must be AVAILABLE"),
        ({"content": "  "}, "non-empty text"),
        ({"storage_uri": "s3://private/artifact"}, "must not use a storage URI"),
        ({"mime_type": "text/plain"}, "MIME type does not match"),
    ],
)
def test_shared_artifact_contract_rejects_invalid_result_envelope(overrides, message):
    job_id, source_id = uuid4(), uuid4()
    artifact = _artifact(ArtifactKind.TEXT, job_id, source_id, **overrides)
    with pytest.raises(ValueError, match=message):
        validate_production_artifact(
            artifact,
            expected_job_id=job_id,
            expected_source_knowledge_unit_id=source_id,
        )


def test_shared_artifact_contract_rejects_wrong_source_or_job():
    job_id, source_id = uuid4(), uuid4()
    wrong_source = _artifact(ArtifactKind.TEXT, job_id, uuid4())
    with pytest.raises(ValueError, match="different source material"):
        validate_production_artifact(
            wrong_source, expected_job_id=job_id, expected_source_knowledge_unit_id=source_id
        )
    wrong_job = _artifact(ArtifactKind.TEXT, uuid4(), source_id)
    with pytest.raises(ValueError, match="different production job"):
        validate_production_artifact(
            wrong_job, expected_job_id=job_id, expected_source_knowledge_unit_id=source_id
        )


def test_shared_artifact_contract_requires_post_reference_and_media_storage():
    job_id, source_id = uuid4(), uuid4()
    post_without_reference = _artifact(ArtifactKind.POST, job_id, source_id, post_id=None)
    with pytest.raises(ValueError, match="canonical Post"):
        validate_production_artifact(
            post_without_reference, expected_job_id=job_id, expected_source_knowledge_unit_id=source_id
        )
    image_without_storage = _artifact(ArtifactKind.IMAGE, job_id, source_id, storage_uri=None)
    with pytest.raises(ValueError, match="storage reference"):
        validate_production_artifact(
            image_without_storage, expected_job_id=job_id, expected_source_knowledge_unit_id=source_id
        )
