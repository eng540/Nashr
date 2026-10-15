"""Safe rendering and validation for editable, versioned AI prompt templates."""
from __future__ import annotations

import re
from collections.abc import Mapping, Set


def template_variables(template: str) -> set[str]:
    return set(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", template))


def validate_template_variables(template: str, required: Set[str]) -> None:
    found = template_variables(template)
    missing = set(required) - found
    unsupported = found - set(required)
    if missing:
        raise ValueError("Prompt template is missing required variables: " + ", ".join(sorted(missing)))
    if unsupported:
        raise ValueError("Prompt template contains unsupported variables: " + ", ".join(sorted(unsupported)))


def render_prompt_template(template: str, values: Mapping[str, object]) -> str:
    """Render explicit placeholders without evaluating text inserted from a source."""
    found = template_variables(template)
    missing_values = set(values) - found
    if missing_values:
        raise ValueError("Prompt template is missing required variables: " + ", ".join(sorted(missing_values)))
    unresolved = found - set(values)
    if unresolved:
        raise ValueError("Prompt template has unresolved variables: " + ", ".join(sorted(unresolved)))
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    if not rendered.strip():
        raise ValueError("Resolved prompt template cannot be empty.")
    return rendered
