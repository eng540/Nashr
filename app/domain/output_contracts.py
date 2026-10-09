"""Versioned output contracts independent of any production capability/provider."""
from dataclasses import dataclass
import re


ARTIFACT_KINDS = frozenset({"POST", "TEXT", "IMAGE", "VIDEO", "AUDIO"})
CONTENT_MODES = frozenset({"INLINE", "STORAGE_URI"})


@dataclass(frozen=True)
class OutputContractDefinition:
    artifact_kind: str
    mime_type: str
    content_mode: str
    required_metadata_fields: tuple[str, ...] = ()
    max_content_chars: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_kind, str) or self.artifact_kind not in ARTIFACT_KINDS:
            raise ValueError("Output contract artifact_kind is unsupported.")
        if not isinstance(self.mime_type, str) or re.fullmatch(r"[A-Za-z0-9!#        if self.artifact_kind not in ARTIFACT_KINDS:
            raise ValueError("Output contract artifact_kind is unsupported.")
        if not isinstance(self.mime_type, str) or "/" not in self.mime_type or self.mime_type.startswith("/") or self.mime_type.endswith("/"):
            raise ValueError("Output contract mime_type must be a valid type/subtype string.")^_.+-]+/[A-Za-z0-9!#        if self.artifact_kind not in ARTIFACT_KINDS:
            raise ValueError("Output contract artifact_kind is unsupported.")
        if not isinstance(self.mime_type, str) or "/" not in self.mime_type or self.mime_type.startswith("/") or self.mime_type.endswith("/"):
            raise ValueError("Output contract mime_type must be a valid type/subtype string.")^_.+-]+", self.mime_type) is None:
            raise ValueError("Output contract mime_type must be a valid type/subtype string.")
        expected_prefix = {
            "POST": "text/",
            "TEXT": "text/",
            "IMAGE": "image/",
            "VIDEO": "video/",
            "AUDIO": "audio/",
        }[self.artifact_kind]
        if not self.mime_type.lower().startswith(expected_prefix):
            raise ValueError(f"Output contract MIME type must match artifact kind {self.artifact_kind}.")
        if not isinstance(self.content_mode, str) or self.content_mode not in CONTENT_MODES:
            raise ValueError("Output contract content_mode must be INLINE or STORAGE_URI.")
        if not isinstance(self.required_metadata_fields, tuple):
            raise ValueError("Output contract required_metadata_fields must be a tuple.")
        if self.artifact_kind in {"POST", "TEXT"} and self.content_mode != "INLINE":
            raise ValueError("POST and TEXT contracts must use INLINE content.")
        if self.artifact_kind in {"IMAGE", "VIDEO", "AUDIO"} and self.content_mode != "STORAGE_URI":
            raise ValueError("Media contracts must use STORAGE_URI content.")
        if self.max_content_chars is not None and (
            isinstance(self.max_content_chars, bool)
            or not isinstance(self.max_content_chars, int)
            or self.max_content_chars < 1
        ):
            raise ValueError("Output contract max_content_chars must be a positive integer or null.")
        if self.content_mode == "STORAGE_URI" and self.max_content_chars is not None:
            raise ValueError("STORAGE_URI contracts cannot define an inline content length.")
        if len(self.required_metadata_fields) != len(set(self.required_metadata_fields)):
            raise ValueError("Output contract required metadata fields must be unique.")
        if any(
            not isinstance(field, str) or re.fullmatch(r"[A-Za-z0-9._-]+", field) is None
            for field in self.required_metadata_fields
        ):
            raise ValueError("Output contract metadata field names must be non-empty identifiers.")

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_kind": self.artifact_kind,
            "mime_type": self.mime_type,
            "content_mode": self.content_mode,
            "required_metadata_fields": list(self.required_metadata_fields),
            "max_content_chars": self.max_content_chars,
        }

    @classmethod
    def from_dict(cls, value: object) -> "OutputContractDefinition":
        if not isinstance(value, dict):
            raise ValueError("Output contract definition must be an object.")
        expected = {"artifact_kind", "mime_type", "content_mode", "required_metadata_fields", "max_content_chars"}
        if set(value) != expected:
            raise ValueError("Output contract definition contains missing or unsupported fields.")
        for field in ("artifact_kind", "mime_type", "content_mode"):
            if not isinstance(value[field], str):
                raise ValueError(f"Output contract {field} must be a string.")
        required = value["required_metadata_fields"]
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
            raise ValueError("Output contract required_metadata_fields must be a list of strings.")
        maximum = value["max_content_chars"]
        if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int)):
            raise ValueError("Output contract max_content_chars must be an integer or null.")
        return cls(
            artifact_kind=value["artifact_kind"],
            mime_type=value["mime_type"],
            content_mode=value["content_mode"],
            required_metadata_fields=tuple(required),
            max_content_chars=maximum,
        )
