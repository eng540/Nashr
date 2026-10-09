"""Declarative, versioned recipe contracts independent of providers and output storage."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RecipeStage:
    key: str
    capability_key: str
    capability_version: int

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.capability_key.strip():
            raise ValueError("Recipe stage and capability keys are required.")
        if isinstance(self.capability_version, bool) or not isinstance(self.capability_version, int) or self.capability_version < 1:
            raise ValueError("Recipe capability version must be positive.")

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "capability_key": self.capability_key,
            "capability_version": self.capability_version,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RecipeStage":
        if not isinstance(value, dict):
            raise ValueError("Recipe stage must be an object.")
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
        return cls(key, capability_key, capability_version)


@dataclass(frozen=True)
class ProductionRecipe:
    key: str
    version: int
    stages: tuple[RecipeStage, ...]

    def __post_init__(self) -> None:
        if not self.key.strip() or isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("Recipe key and positive version are required.")
        if not self.stages:
            raise ValueError("A production recipe must contain at least one stage.")
        keys = [stage.key for stage in self.stages]
        if len(keys) != len(set(keys)):
            raise ValueError("Recipe stage keys must be unique.")

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "version": self.version,
            "stages": [stage.to_dict() for stage in self.stages],
        }

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
        return cls(key, version, tuple(RecipeStage.from_dict(stage) for stage in stages))


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
