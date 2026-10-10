"""Declarative production policy rules; configuration is data, never executable code."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductionPolicyDefinition:
    min_content_chars: int = 1
    max_content_chars: int = 100000
    required_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    allow_urls: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.min_content_chars, bool) or not isinstance(self.min_content_chars, int) or self.min_content_chars < 0:
            raise ValueError("Policy min_content_chars must be a non-negative integer.")
        if isinstance(self.max_content_chars, bool) or not isinstance(self.max_content_chars, int) or self.max_content_chars < 1:
            raise ValueError("Policy max_content_chars must be a positive integer.")
        if self.min_content_chars > self.max_content_chars:
            raise ValueError("Policy minimum content length cannot exceed maximum content length.")
        if not isinstance(self.allow_urls, bool):
            raise ValueError("Policy allow_urls must be a boolean.")
        for field in ("required_terms", "forbidden_terms"):
            terms = getattr(self, field)
            if not isinstance(terms, tuple) or any(not isinstance(term, str) or not term.strip() for term in terms):
                raise ValueError(f"Policy {field} must contain non-empty strings.")
            normalized = [term.casefold().strip() for term in terms]
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"Policy {field} must not contain duplicate terms.")
        required = {term.casefold().strip() for term in self.required_terms}
        forbidden = {term.casefold().strip() for term in self.forbidden_terms}
        if required & forbidden:
            raise ValueError("A policy term cannot be both required and forbidden.")

    def to_dict(self) -> dict[str, object]:
        return {
            "min_content_chars": self.min_content_chars,
            "max_content_chars": self.max_content_chars,
            "required_terms": [term.strip() for term in self.required_terms],
            "forbidden_terms": [term.strip() for term in self.forbidden_terms],
            "allow_urls": self.allow_urls,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProductionPolicyDefinition":
        if not isinstance(value, dict):
            raise ValueError("Policy definition must be an object.")
        expected = {"min_content_chars", "max_content_chars", "required_terms", "forbidden_terms", "allow_urls"}
        if set(value) != expected:
            raise ValueError("Policy definition contains missing or unsupported fields.")
        for field in ("min_content_chars", "max_content_chars"):
            if isinstance(value[field], bool) or not isinstance(value[field], int):
                raise ValueError(f"Policy {field} must be an integer.")
        for field in ("required_terms", "forbidden_terms"):
            if not isinstance(value[field], list) or any(not isinstance(term, str) for term in value[field]):
                raise ValueError(f"Policy {field} must be a list of strings.")
        if not isinstance(value["allow_urls"], bool):
            raise ValueError("Policy allow_urls must be a boolean.")
        return cls(
            min_content_chars=value["min_content_chars"],
            max_content_chars=value["max_content_chars"],
            required_terms=tuple(value["required_terms"]),
            forbidden_terms=tuple(value["forbidden_terms"]),
            allow_urls=value["allow_urls"],
        )
