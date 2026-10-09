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
