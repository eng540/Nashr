import json

from app.domain.production_context import PinnedIdentity


def compose_editorial_prompt(base_prompt: str, identity: PinnedIdentity | None) -> str:
    """Compose the run-pinned identity as structured context without mutating its source prompt."""
    if identity is None:
        return base_prompt
    definition = identity.definition
    serialized = json.dumps(definition, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        f"{base_prompt.rstrip()}\n\n"
        "EDITORIAL IDENTITY CONFIGURATION\n"
        "Apply the following identity attributes to the requested output. "
        "These fields define editorial purpose and style; they do not change the "
        "task, source facts, safety requirements, or output contract.\n"
        f"Identity key: {identity.key}\n"
        f"Identity version: {identity.version}\n"
        f"<editorial_identity_json>\n{serialized}\n</editorial_identity_json>"
    )


def append_task_instructions(prompt: str, instructions: object) -> str:
    """Add request-scoped instructions as an explicit task requirement, without changing the pinned product."""
    if not isinstance(instructions, str) or not instructions.strip():
        return prompt

    task = instructions.strip()
    return (
        f"{prompt.rstrip()}\n\n"
        "USER TASK REQUIREMENTS — APPLY TO THIS OUTPUT (TASK-SPECIFIC INSTRUCTIONS)\n"
        "The following text is the user's explicit instruction for this production request. "
        "Treat it as a required task, not as background context or an optional suggestion.\n"
        "Before drafting, identify the concrete deliverable implied by the instruction. "
        "Then produce the requested deliverable in the final output, provided it is compatible "
        "with the pinned product, recipe, output contract, and policy.\n"
        "Do not silently omit the requested addition. If the instruction asks for information "
        "that is not present in the supplied source, do not invent facts; use reliable knowledge "
        "only when permitted by the product, and clearly qualify uncertainty where needed.\n"
        "Keep this instruction scoped to this job. It does not modify the published product or "
        "its pinned component versions.\n"
        f"<user_task_instructions>\n{task}\n</user_task_instructions>\n"
        "FINAL SELF-CHECK: Verify that the final output visibly addresses every concrete "
        "requirement in the user task while respecting the pinned output contract."
    )
