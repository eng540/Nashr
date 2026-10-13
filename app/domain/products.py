"""Versioned product configuration and immutable component references."""
from dataclasses import dataclass
from uuid import UUID


_MANIFEST_COMPONENTS = {"prompt", "identity", "recipe", "policy", "output_contract"}


@dataclass(frozen=True)
class ProductionProductDefinition:
    recipe_key: str
    output_contract_key: str
    policy_key: str
    audience: str
    experience: str
    prompt_key: str | None = None
    identity_key: str | None = None
    component_versions: dict[str, dict[str, object]] | None = None

    def __post_init__(self) -> None:
        for field in ("recipe_key", "output_contract_key", "policy_key", "audience", "experience"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Product {field} is required.")
        for field in ("recipe_key", "output_contract_key", "policy_key"):
            if len(getattr(self, field)) > 200:
                raise ValueError(f"Product {field} cannot exceed 200 characters.")
        for field in ("audience", "experience"):
            if len(getattr(self, field)) > 2000:
                raise ValueError(f"Product {field} cannot exceed 2000 characters.")
        for field in ("prompt_key", "identity_key"):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 200):
                raise ValueError(f"Product {field} must be a non-empty component key when provided.")
        if self.component_versions is not None:
            refs = self.component_versions
            if not isinstance(refs, dict) or set(refs) != _MANIFEST_COMPONENTS:
                raise ValueError("Product component manifest must reference prompt, identity, recipe, policy, and output_contract.")
            expected_keys = {
                "prompt": self.prompt_key,
                "identity": self.identity_key,
                "recipe": self.recipe_key,
                "policy": self.policy_key,
                "output_contract": self.output_contract_key,
            }
            for component, reference in refs.items():
                if not isinstance(reference, dict) or set(reference) != {"key", "version_id", "version"}:
                    raise ValueError(f"Product manifest reference '{component}' must contain key, version_id, and version.")
                key, version_id, version = reference["key"], reference["version_id"], reference["version"]
                if not isinstance(key, str) or not key.strip() or key != expected_keys[component]:
                    raise ValueError(f"Product manifest reference '{component}' does not match its declared component key.")
                if not isinstance(version_id, str):
                    raise ValueError(f"Product manifest reference '{component}' requires a version ID.")
                try:
                    UUID(version_id)
                except ValueError as exc:
                    raise ValueError(f"Product manifest reference '{component}' has an invalid version ID.") from exc
                if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                    raise ValueError(f"Product manifest reference '{component}' requires a positive version number.")

    @property
    def has_immutable_manifest(self) -> bool:
        return self.component_versions is not None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "recipe_key": self.recipe_key.strip(),
            "output_contract_key": self.output_contract_key.strip(),
            "policy_key": self.policy_key.strip(),
            "audience": self.audience.strip(),
            "experience": self.experience.strip(),
        }
        if self.prompt_key is not None:
            value["prompt_key"] = self.prompt_key.strip()
        if self.identity_key is not None:
            value["identity_key"] = self.identity_key.strip()
        if self.component_versions is not None:
            value["component_versions"] = {
                key: dict(reference) for key, reference in self.component_versions.items()
            }
        return value

    @classmethod
    def from_dict(cls, value: object) -> "ProductionProductDefinition":
        if not isinstance(value, dict):
            raise ValueError("Product definition must be an object.")
        required = {"recipe_key", "output_contract_key", "policy_key", "audience", "experience"}
        optional = {"prompt_key", "identity_key", "component_versions"}
        if not required.issubset(value) or set(value) - required - optional:
            raise ValueError("Product definition contains missing or unsupported fields.")
        if any(not isinstance(value[field], str) for field in required):
            raise ValueError("All required product definition fields must be strings.")
        for field in ("prompt_key", "identity_key"):
            if field in value and value[field] is not None and not isinstance(value[field], str):
                raise ValueError(f"Product {field} must be a string or null.")
        component_versions = value.get("component_versions")
        if component_versions is not None and not isinstance(component_versions, dict):
            raise ValueError("Product component_versions must be an object.")
        return cls(
            **{field: value[field] for field in required},
            prompt_key=value.get("prompt_key"),
            identity_key=value.get("identity_key"),
            component_versions=component_versions,
        )
