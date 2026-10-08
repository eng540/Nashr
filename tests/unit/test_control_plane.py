from app.domain.control_plane import ResolvedPrompt


def test_resolved_prompt_carries_runtime_version_and_body():
    prompt = ResolvedPrompt(key="editorial.drafter", version=3, body="resolved")
    assert prompt.key == "editorial.drafter"
    assert prompt.version == 3
    assert prompt.body == "resolved"
