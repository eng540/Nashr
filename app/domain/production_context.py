"""Validated, immutable snapshot of the configuration resolved for a production run."""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.domain.recipes import ProductionRecipe
from app.domain.identities import EditorialIdentityDefinition
from app.domain.output_contracts import OutputContractDefinition

CONTEXT_SCHEMA_VERSION = 4
SUPPORTED_CONTEXT_SCHEMA_VERSIONS = (1, 2, 3, 4)
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
        if not self.key.strip() or isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1 or not self.body.strip():
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
class PinnedIdentity:
    identity_id: str
    version_id: str
    key: str
    version: int
    definition: dict[str, object]

    def __post_init__(self) -> None:
        try:
            UUID(self.identity_id)
            UUID(self.version_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Pinned identity requires valid identity and version IDs.") from exc
        if not self.key.strip() or isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("Pinned identity key and positive version are required.")
        EditorialIdentityDefinition.from_dict(self.definition)

    def to_dict(self) -> dict[str, object]:
        return {
            "identity_id": self.identity_id,
            "version_id": self.version_id,
            "key": self.key,
            "version": self.version,
            "definition": EditorialIdentityDefinition.from_dict(self.definition).to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "PinnedIdentity":
        if not isinstance(value, dict):
            raise ValueError("Resolved context identity must be an object.")
        try:
            identity_id = value["identity_id"]
            version_id = value["version_id"]
            key = value["key"]
            version = value["version"]
            definition = value["definition"]
        except KeyError as exc:
            raise ValueError(f"Resolved context identity is missing {exc.args[0]}.") from exc
        if not all(isinstance(item, str) for item in (identity_id, version_id, key)):
            raise ValueError("Resolved context identity IDs and key must be strings.")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("Resolved context identity version must be an integer.")
        if not isinstance(definition, dict):
            raise ValueError("Resolved context identity definition must be an object.")
        return cls(identity_id, version_id, key, version, definition)


@dataclass(frozen=True)
class PinnedOutputContract:
    contract_id: str
    version_id: str
    key: str
    version: int
    definition: dict[str, object]

    def __post_init__(self) -> None:
        try:
            UUID(self.contract_id)
            UUID(self.version_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Pinned output contract requires valid contract and version IDs.") from exc
        if not self.key.strip() or isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("Pinned output contract key and positive version are required.")
        OutputContractDefinition.from_dict(self.definition)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "version_id": self.version_id,
            "key": self.key,
            "version": self.version,
            "definition": OutputContractDefinition.from_dict(self.definition).to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "PinnedOutputContract":
        if not isinstance(value, dict):
            raise ValueError("Resolved context output_contract must be an object.")
        try:
            contract_id = value["contract_id"]
            version_id = value["version_id"]
            key = value["key"]
            version = value["version"]
            definition = value["definition"]
        except KeyError as exc:
            raise ValueError(f"Resolved context output_contract is missing {exc.args[0]}.") from exc
        if not all(isinstance(item, str) for item in (contract_id, version_id, key)):
            raise ValueError("Resolved context output contract IDs and key must be strings.")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("Resolved context output contract version must be an integer.")
        if not isinstance(definition, dict):
            raise ValueError("Resolved context output contract definition must be an object.")
        return cls(contract_id, version_id, key, version, definition)


@dataclass(frozen=True)
class ResolvedProductionContext:
    schema_version: int
    origin: str
    captured_at: str | None
    prompt_template: PinnedPrompt
    recipe: ProductionRecipe | None = None
    identity: PinnedIdentity | None = None
    output_contract: PinnedOutputContract | None = None

    @classmethod
    def capture(
        cls,
        prompt,
        *,
        recipe: ProductionRecipe | None = None,
        identity: PinnedIdentity | None = None,
        output_contract: PinnedOutputContract | None = None,
        captured_at: datetime | None = None,
    ) -> "ResolvedProductionContext":
        if prompt.template_id is None or prompt.version_id is None:
            raise ValueError("Resolved prompt must include template and version IDs.")
        timestamp = captured_at or datetime.now(timezone.utc)
        return cls(
            schema_version=4 if output_contract is not None else 3 if identity is not None else 2 if recipe is not None else 1,
            origin=RUNTIME_RESOLUTION,
            captured_at=timestamp.astimezone(timezone.utc).isoformat(),
            prompt_template=PinnedPrompt(
                template_id=str(prompt.template_id),
                version_id=str(prompt.version_id),
                key=prompt.key,
                version=prompt.version,
                body=prompt.body,
            ),
            recipe=recipe,
            identity=identity,
            output_contract=output_contract,
        )

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version not in SUPPORTED_CONTEXT_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported resolved production context schema version: {self.schema_version}.")
        if self.origin not in (RUNTIME_RESOLUTION, LEGACY_PIN_BACKFILL):
            raise ValueError("Resolved context origin is invalid.")
        if self.captured_at is not None:
            try:
                datetime.fromisoformat(self.captured_at)
            except ValueError as exc:
                raise ValueError("Resolved context captured_at must be an ISO-8601 timestamp or null.") from exc
        if self.schema_version == 1 and (self.recipe is not None or self.identity is not None or self.output_contract is not None):
            raise ValueError("Resolved context schema version 1 cannot contain recipe, identity, or output contract.")
        if self.schema_version == 2 and (self.recipe is None or self.identity is not None or self.output_contract is not None):
            raise ValueError("Resolved context schema version 2 requires a recipe and cannot contain identity or output contract.")
        if self.schema_version == 3 and (self.recipe is None or self.identity is None or self.output_contract is not None):
            raise ValueError("Resolved context schema version 3 requires pinned recipe and identity and cannot contain output contract.")
        if self.schema_version == 4 and (self.recipe is None or self.output_contract is None):
            raise ValueError("Resolved context schema version 4 requires pinned recipe and output contract.")

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": self.schema_version,
            "origin": self.origin,
            "captured_at": self.captured_at,
            "prompt_template": self.prompt_template.to_dict(),
        }
        if self.schema_version >= 2 and self.recipe is not None:
            value["recipe"] = self.recipe.to_dict()
        if self.schema_version >= 3 and self.identity is not None:
            value["identity"] = self.identity.to_dict()
        if self.schema_version >= 4 and self.output_contract is not None:
            value["output_contract"] = self.output_contract.to_dict()
        return value

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
        if schema_version not in SUPPORTED_CONTEXT_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported resolved production context schema version: {schema_version}.")
        if schema_version == 1:
            if "recipe" in value or "identity" in value or "output_contract" in value:
                raise ValueError("Resolved context schema version 1 cannot contain recipe, identity, or output contract.")
            recipe = None
            identity = None
            output_contract = None
        elif schema_version == 2:
            if "recipe" not in value:
                raise ValueError("Resolved context schema version 2 is missing recipe.")
            if "identity" in value or "output_contract" in value:
                raise ValueError("Resolved context schema version 2 cannot contain identity or output contract.")
            recipe = ProductionRecipe.from_dict(value["recipe"])
            identity = None
            output_contract = None
        elif schema_version == 3:
            if "recipe" not in value or "identity" not in value or "output_contract" in value:
                raise ValueError("Resolved context schema version 3 requires recipe and identity and cannot contain output contract.")
            recipe = ProductionRecipe.from_dict(value["recipe"])
            identity = PinnedIdentity.from_dict(value["identity"])
            output_contract = None
        else:
            if "recipe" not in value or "output_contract" not in value:
                raise ValueError("Resolved context schema version 4 requires recipe and output_contract.")
            recipe = ProductionRecipe.from_dict(value["recipe"])
            identity = PinnedIdentity.from_dict(value["identity"]) if "identity" in value else None
            output_contract = PinnedOutputContract.from_dict(value["output_contract"])
        return cls(
            schema_version=schema_version,
            origin=origin,
            captured_at=captured_at,
            prompt_template=PinnedPrompt.from_dict(prompt_value),
            recipe=recipe,
            identity=identity,
            output_contract=output_contract,
        )
