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
    """Append request-scoped instructions while retaining pinned product constraints."""
    if not isinstance(instructions, str) or not instructions.strip():
        return prompt
    return (
        f"{prompt.rstrip()}\\n\\n"
        "TASK-SPECIFIC INSTRUCTIONS (request scope only)\\n"
        "Apply these instructions where compatible with the pinned product, recipe, "
        "output contract, and policy. Do not replace or override those constraints.\\n"
        f"{instructions.strip()}"
    )
