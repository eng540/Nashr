"""Versioned editorial identity data, independent of recipes and providers."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EditorialIdentityDefinition:
    purpose: str
    audience: str
    voice: str
    tone: str
    principles: tuple[str, ...]
    objectives: tuple[str, ...]
    constraints: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("purpose", "audience", "voice", "tone"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Identity {name} is required.")
        for name in ("principles", "objectives", "constraints"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"Identity {name} must contain non-empty strings.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose.strip(),
            "audience": self.audience.strip(),
            "voice": self.voice.strip(),
            "tone": self.tone.strip(),
            "principles": [item.strip() for item in self.principles],
            "objectives": [item.strip() for item in self.objectives],
            "constraints": [item.strip() for item in self.constraints],
        }

    @classmethod
    def from_dict(cls, value: object) -> "EditorialIdentityDefinition":
        if not isinstance(value, dict):
            raise ValueError("Identity definition must be an object.")
        expected_fields = {"purpose", "audience", "voice", "tone", "principles", "objectives", "constraints"}
        if set(value) != expected_fields:
            raise ValueError("Identity definition contains missing or unsupported fields.")
        scalar_fields = ("purpose", "audience", "voice", "tone")
        if any(not isinstance(value.get(field), str) for field in scalar_fields):
            raise ValueError("Identity purpose, audience, voice, and tone must be strings.")
        list_fields = ("principles", "objectives", "constraints")
        if any(not isinstance(value.get(field), list) for field in list_fields):
            raise ValueError("Identity principles, objectives, and constraints must be lists.")
        if any(any(not isinstance(item, str) for item in value[field]) for field in list_fields):
            raise ValueError("Identity list fields must contain strings.")
        return cls(
            purpose=value["purpose"],
            audience=value["audience"],
            voice=value["voice"],
            tone=value["tone"],
            principles=tuple(value["principles"]),
            objectives=tuple(value["objectives"]),
            constraints=tuple(value["constraints"]),
        )
