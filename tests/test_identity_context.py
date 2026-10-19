from app.application.identity_context import append_task_instructions


def test_task_instructions_are_explicit_required_job_scoped_requirements():
    prompt = append_task_instructions(
        "Pinned product prompt",
        "إضافة نبذه عن عمر بن الخطاب",
    )

    assert prompt.startswith("Pinned product prompt")
    assert "USER TASK REQUIREMENTS — APPLY TO THIS OUTPUT" in prompt
    assert "Treat it as a required task" in prompt
    assert "إضافة نبذه عن عمر بن الخطاب" in prompt
    assert "<user_task_instructions>" in prompt
    assert "FINAL SELF-CHECK" in prompt
    assert "does not modify the published product" in prompt


def test_empty_task_instructions_do_not_change_pinned_prompt():
    prompt = "Pinned product prompt"

    assert append_task_instructions(prompt, None) == prompt
    assert append_task_instructions(prompt, "  ") == prompt
    assert append_task_instructions(prompt, 123) == prompt
