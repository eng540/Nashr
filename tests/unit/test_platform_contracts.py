from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.artifacts import Artifact, ArtifactKind
from app.domain.control_plane import ResolvedPrompt


def test_artifact_contract_is_provider_neutral_and_keeps_post_as_first_kind():
    field_names = {field.name for field in fields(Artifact)}

    assert {
        "id",
        "source_knowledge_unit_id",
        "kind",
        "content",
        "status",
        "created_at",
        "updated_at",
    } <= field_names
    assert ArtifactKind.POST.value == "POST"
    assert not {
        "telegram_chat_id",
        "telegram_message_id",
        "provider",
        "provider_payload",
    } & field_names


def test_artifact_contract_is_immutable():
    now = datetime.now(timezone.utc)
    artifact = Artifact(
        id=uuid4(),
        source_knowledge_unit_id=uuid4(),
        kind=ArtifactKind.POST,
        content="محتوى تجريبي",
        status="DRAFT",
        created_at=now,
        updated_at=now,
    )

    with pytest.raises(FrozenInstanceError):
        artifact.content = "changed"  # type: ignore[misc]


def test_resolved_prompt_pins_key_version_and_body_as_one_value():
    prompt = ResolvedPrompt(key="editorial.drafter", version=4, body="prompt v4")

    assert (prompt.key, prompt.version, prompt.body) == (
        "editorial.drafter",
        4,
        "prompt v4",
    )

    with pytest.raises(FrozenInstanceError):
        prompt.version = 5  # type: ignore[misc]
