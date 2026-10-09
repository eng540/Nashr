"""Validated, immutable snapshot of the configuration resolved for a production run."""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

CONTEXT_SCHEMA_VERSION = 1
RUNTIME_RESOLUTION = "RUNTIME_RESOLUTION"
LEGACY_PIN_BACKFILL = "LEGACY_PIN_BACKFILL"


@dataclass(frozen=True)
class PinnedPrompt:
    template_id: str
    version_id: str
    key: str
    version: int
    body: str

    def __post_init__(self) -> None:
        try:
            UUID(self.template_id)
            UUID(self.version_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Pinned prompt requires valid template and version IDs.") from exc
        if not self.key.strip() or self.version < 1 or not self.body.strip():
            raise ValueError("Pinned prompt key, positive version, and body are required.")

    def to_dict(self) -> dict[str, object]:
        return {
            "template_id": self.template_id,
            "version_id": self.version_id,
            "key": self.key,
            "version": self.version,
            "body": self.body,
        }

    @classmethod
    def from_dict(cls, value: object) -> "PinnedPrompt":
        if not isinstance(value, dict):
            raise ValueError("Resolved context prompt_template must be an object.")
        try:
            template_id = value["template_id"]
            version_id = value["version_id"]
            key = value["key"]
            version = value["version"]
            body = value["body"]
        except KeyError as exc:
            raise ValueError(f"Resolved context prompt_template is missing {exc.args[0]}.") from exc
        if not all(isinstance(item, str) for item in (template_id, version_id, key, body)):
            raise ValueError("Resolved context prompt fields must be strings.")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("Resolved context prompt version must be an integer.")
        return cls(template_id, version_id, key, version, body)


@dataclass(frozen=True)
class ResolvedProductionContext:
    schema_version: int
    origin: str
    captured_at: str | None
    prompt_template: PinnedPrompt

    @classmethod
    def capture(cls, prompt, *, captured_at: datetime | None = None) -> "ResolvedProductionContext":
        if prompt.template_id is None or prompt.version_id is None:
            raise ValueError("Resolved prompt must include template and version IDs.")
        timestamp = captured_at or datetime.now(timezone.utc)
        return cls(
            schema_version=CONTEXT_SCHEMA_VERSION,
            origin=RUNTIME_RESOLUTION,
            captured_at=timestamp.astimezone(timezone.utc).isoformat(),
            prompt_template=PinnedPrompt(
                template_id=str(prompt.template_id),
                version_id=str(prompt.version_id),
                key=prompt.key,
                version=prompt.version,
                body=prompt.body,
            ),
        )

    def __post_init__(self) -> None:
        if self.schema_version != CONTEXT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported resolved production context schema version: {self.schema_version}.")
        if self.origin not in (RUNTIME_RESOLUTION, LEGACY_PIN_BACKFILL):
            raise ValueError("Resolved context origin is invalid.")
        if self.captured_at is not None:
            try:
                datetime.fromisoformat(self.captured_at)
            except ValueError as exc:
                raise ValueError("Resolved context captured_at must be an ISO-8601 timestamp or null.") from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "origin": self.origin,
            "captured_at": self.captured_at,
            "prompt_template": self.prompt_template.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "ResolvedProductionContext":
        if not isinstance(value, dict):
            raise ValueError("Resolved production context must be an object.")
        try:
            schema_version = value["schema_version"]
            origin = value["origin"]
            captured_at = value["captured_at"]
            prompt_value = value["prompt_template"]
        except KeyError as exc:
            raise ValueError(f"Resolved production context is missing {exc.args[0]}.") from exc
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise ValueError("Resolved context schema_version must be an integer.")
        if not isinstance(origin, str):
            raise ValueError("Resolved context origin must be a string.")
        if captured_at is not None and not isinstance(captured_at, str):
            raise ValueError("Resolved context captured_at must be a string or null.")
        return cls(
            schema_version=schema_version,
            origin=origin,
            captured_at=captured_at,
            prompt_template=PinnedPrompt.from_dict(prompt_value),
        )
