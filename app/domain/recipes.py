"""Declarative, versioned recipe contracts independent of providers and output storage."""
from dataclasses import dataclass, field
import json
from uuid import UUID

SUPPORTED_RECIPE_CAPABILITIES = frozenset({("produce_post", 1)})


@dataclass(frozen=True)
class RecipeStage:
    key: str
    capability_key: str
    capability_version: int
    configuration: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.capability_key.strip():
            raise ValueError("Recipe stage and capability keys are required.")
        if isinstance(self.capability_version, bool) or not isinstance(self.capability_version, int) or self.capability_version < 1:
            raise ValueError("Recipe capability version must be a positive integer.")
        if not isinstance(self.configuration, dict) or any(not isinstance(key, str) for key in self.configuration):
            raise ValueError("Recipe stage configuration must be a JSON object with string keys.")
        try:
            json.dumps(self.configuration, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Recipe stage configuration must contain JSON-compatible values only.") from exc

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "key": self.key,
            "capability_key": self.capability_key,
            "capability_version": self.capability_version,
        }
        if self.configuration:
            value["configuration"] = dict(self.configuration)
        return value

    @classmethod
    def from_dict(cls, value: object) -> "RecipeStage":
        if not isinstance(value, dict):
            raise ValueError("Recipe stage must be an object.")
        unknown = set(value) - {"key", "capability_key", "capability_version", "configuration"}
        if unknown:
            raise ValueError("Recipe stage contains unsupported fields: " + ", ".join(sorted(unknown)))
        try:
            key, capability_key, capability_version = (
                value["key"], value["capability_key"], value["capability_version"]
            )
        except KeyError as exc:
            raise ValueError(f"Recipe stage is missing {exc.args[0]}.") from exc
        if not isinstance(key, str) or not isinstance(capability_key, str):
            raise ValueError("Recipe stage keys must be strings.")
        if isinstance(capability_version, bool) or not isinstance(capability_version, int):
            raise ValueError("Recipe capability version must be an integer.")
        configuration = value.get("configuration", {})
        if not isinstance(configuration, dict):
            raise ValueError("Recipe stage configuration must be an object.")
        return cls(key, capability_key, capability_version, configuration)


@dataclass(frozen=True)
class ProductionRecipe:
    key: str
    version: int
    stages: tuple[RecipeStage, ...]
    recipe_id: str | None = None
    version_id: str | None = None

    def __post_init__(self) -> None:
        if not self.key.strip() or isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("Recipe key and positive version are required.")
        if not self.stages:
            raise ValueError("A production recipe must contain at least one stage.")
        keys = [stage.key for stage in self.stages]
        if len(keys) != len(set(keys)):
            raise ValueError("Recipe stage keys must be unique.")
        if (self.recipe_id is None) != (self.version_id is None):
            raise ValueError("Recipe and recipe-version IDs must be supplied together.")
        if self.recipe_id is not None and self.version_id is not None:
            try:
                UUID(self.recipe_id)
                UUID(self.version_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("Recipe requires valid recipe and version IDs.") from exc

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "key": self.key,
            "version": self.version,
            "stages": [stage.to_dict() for stage in self.stages],
        }
        if self.recipe_id is not None and self.version_id is not None:
            value["recipe_id"] = self.recipe_id
            value["version_id"] = self.version_id
        return value

    @classmethod
    def from_dict(cls, value: object) -> "ProductionRecipe":
        if not isinstance(value, dict):
            raise ValueError("Pinned recipe must be an object.")
        try:
            key, version, stages = value["key"], value["version"], value["stages"]
        except KeyError as exc:
            raise ValueError(f"Pinned recipe is missing {exc.args[0]}.") from exc
        if not isinstance(key, str):
            raise ValueError("Recipe key must be a string.")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("Recipe version must be an integer.")
        if not isinstance(stages, list):
            raise ValueError("Recipe stages must be a list.")
        recipe_id, version_id = value.get("recipe_id"), value.get("version_id")
        if recipe_id is not None and not isinstance(recipe_id, str):
            raise ValueError("Recipe ID must be a string or null.")
        if version_id is not None and not isinstance(version_id, str):
            raise ValueError("Recipe version ID must be a string or null.")
        return cls(
            key,
            version,
            tuple(RecipeStage.from_dict(stage) for stage in stages),
            recipe_id=recipe_id,
            version_id=version_id,
        )


BOOK_TO_TELEGRAM_POST = ProductionRecipe(
    key="BOOK_TO_TELEGRAM_POST",
    version=1,
    stages=(
        RecipeStage(
            key="produce-post",
            capability_key="produce_post",
            capability_version=1,
        ),
    ),
)


def validate_recipe_stage_configuration(stage: RecipeStage) -> None:
    """Validate only the public configuration contract of built-in capabilities."""
    if stage.capability_key == "produce_post" and stage.capability_version == 1:
        unknown = set(stage.configuration) - {"style_instructions"}
        if unknown:
            raise ValueError("produce_post configuration contains unsupported fields: " + ", ".join(sorted(unknown)))
        instructions = stage.configuration.get("style_instructions")
        if instructions is not None and (
            not isinstance(instructions, str) or not instructions.strip() or len(instructions) > 2000
        ):
            raise ValueError("produce_post style_instructions must be a non-empty string up to 2000 characters.")
    elif stage.configuration:
        raise ValueError(
            f"Configuration is not defined for capability '{stage.capability_key}' v{stage.capability_version}."
        )
