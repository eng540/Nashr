"""Versioned product definitions compose existing control-plane contracts."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductionProductDefinition:
    recipe_key: str
    output_contract_key: str
    policy_key: str
    audience: str
    experience: str

    def __post_init__(self) -> None:
        for field in ("recipe_key", "output_contract_key", "policy_key", "audience", "experience"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Product {field} is required.")
        for field in ("recipe_key", "output_contract_key", "policy_key"):
            value = getattr(self, field)
            if len(value) > 200:
                raise ValueError(f"Product {field} cannot exceed 200 characters.")
        for field in ("audience", "experience"):
            if len(getattr(self, field)) > 2000:
                raise ValueError(f"Product {field} cannot exceed 2000 characters.")

    def to_dict(self) -> dict[str, object]:
        return {
            "recipe_key": self.recipe_key.strip(),
            "output_contract_key": self.output_contract_key.strip(),
            "policy_key": self.policy_key.strip(),
            "audience": self.audience.strip(),
            "experience": self.experience.strip(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProductionProductDefinition":
        if not isinstance(value, dict):
            raise ValueError("Product definition must be an object.")
        expected = {"recipe_key", "output_contract_key", "policy_key", "audience", "experience"}
        if set(value) != expected:
            raise ValueError("Product definition contains missing or unsupported fields.")
        if any(not isinstance(value[field], str) for field in expected):
            raise ValueError("All product definition fields must be strings.")
        return cls(**{field: value[field] for field in expected})
