from sqlalchemy.exc import IntegrityError

from app.domain.products import ProductionProductDefinition
from app.domain.output_contracts import OutputContractDefinition
from app.infrastructure.database.products import ProductionProductRepository
from app.infrastructure.artifact_storage import ArtifactStorageConfigurationError, ArtifactStorageError, S3ArtifactStorage
from app.application.control_plane import ControlPlaneResolver
from app.infrastructure.database.models import ProductionProductModel, ProductionProductVersionModel


def _version_payload(row) -> dict[str, object]:
    return {
        "id": str(row.id), "product_id": str(row.product_id), "version": row.version,
        "definition": ProductionProductDefinition.from_dict(row.definition).to_dict(),
        "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _product_payload(row, versions: list | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(row.id), "key": row.key, "name": row.name, "purpose": row.purpose,
        "parent_product_id": str(row.parent_product_id) if row.parent_product_id else None,
        "derived_from_version_id": str(row.derived_from_version_id) if row.derived_from_version_id else None,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }
    if versions is not None:
        payload["versions"] = [_version_payload(version) for version in versions]
        payload["active_version"] = next((version.version for version in versions if version.status == "PUBLISHED"), None)
    return payload


class ProductionProductControlPlaneService:
    def __init__(self, session) -> None:
        self.repository = ProductionProductRepository(session)
        self.session = session

    async def list_products(self) -> list[dict[str, object]]:
        rows = await self.repository.list_products()
        return [_product_payload(row, await self.repository.get_versions(row.key)) for row in rows]

    async def get_product(self, key: str) -> dict[str, object]:
        row = await self.repository.get_product(key)
        if row is None:
            raise LookupError("Production product not found.")
        versions = await self.repository.get_versions(key)
        payload = _product_payload(row, versions)
        if row.parent_product_id is not None and row.derived_from_version_id is not None:
            parent = await self.session.get(ProductionProductModel, row.parent_product_id)
            source_version = await self.session.get(ProductionProductVersionModel, row.derived_from_version_id)
            if parent is not None and source_version is not None:
                source_definition = ProductionProductDefinition.from_dict(source_version.definition).to_dict()
                current_version = max(versions, key=lambda version: version.version) if versions else None
                current_definition = ProductionProductDefinition.from_dict(current_version.definition).to_dict() if current_version else {}
                fields = sorted((set(source_definition) | set(current_definition)) - {"component_versions"})
                changes = {
                    field: {"from": source_definition.get(field), "to": current_definition.get(field)}
                    for field in fields
                    if source_definition.get(field) != current_definition.get(field)
                }
                source_refs = source_definition.get("component_versions") or {}
                current_refs = current_definition.get("component_versions") or {}
                component_diffs = {
                    component: {"from": source_refs.get(component), "to": current_refs.get(component)}
                    for component in sorted(set(source_refs) | set(current_refs))
                    if source_refs.get(component) != current_refs.get(component)
                }
                payload["derivation"] = {
                    "parent_product_key": parent.key,
                    "source_version": source_version.version,
                    "source_version_id": str(source_version.id),
                    "changes": changes,
                    "component_diffs": component_diffs,
                }
        return payload

    async def derive_product(
        self, source_key: str, source_version_number: int, key: str, name: str, purpose: str
    ) -> dict[str, object]:
        source = await self.repository.get_product(source_key)
        if source is None:
            raise LookupError("Source product not found.")
        if not key.strip() or not name.strip() or not purpose.strip():
            raise ValueError("Derived product key, name, and purpose are required.")
        if await self.repository.get_product(key):
            raise ValueError("Derived product key already exists.")
        source_versions = await self.repository.get_versions(source_key)
        source_version = next((version for version in source_versions if version.version == source_version_number), None)
        if source_version is None:
            raise LookupError("Source product version not found.")
        if source_version.status not in {"PUBLISHED", "ARCHIVED"}:
            raise ValueError("A product can only be derived from a published product version.")
        definition = ProductionProductDefinition.from_dict(source_version.definition)
        if not definition.has_immutable_manifest:
            raise ValueError("Upgrade and publish this legacy product version before deriving it; component versions are not pinned.")
        try:
            product, version = await self.repository.create_product(
                key.strip(),
                name.strip(),
                purpose.strip(),
                definition.to_dict(),
                parent_product_id=source.id,
                derived_from_version_id=source_version.id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Derived product key already exists.") from exc
        await self.session.refresh(product)
        await self.session.refresh(version)
        return {**_product_payload(product, [version]), "created_version": _version_payload(version)}

    async def create_product(self, key: str, name: str, purpose: str, definition: dict[str, object]) -> dict[str, object]:
        definition = ProductionProductDefinition.from_dict(definition).to_dict()
        if not name.strip() or not purpose.strip():
            raise ValueError("Production product name and purpose are required.")
        if await self.repository.get_product(key):
            raise ValueError("Production product key already exists.")
        try:
            row, version = await self.repository.create_product(key.strip(), name.strip(), purpose.strip(), definition)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Production product key already exists.") from exc
        await self.session.refresh(row)
        await self.session.refresh(version)
        return {**_product_payload(row), "created_version": _version_payload(version)}

    async def create_draft(self, key: str, definition: dict[str, object]) -> dict[str, object]:
        row = await self.repository.create_draft(key, ProductionProductDefinition.from_dict(definition).to_dict())
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def update_draft(self, key: str, version: int, definition: dict[str, object]) -> dict[str, object]:
        row = await self.repository.update_draft(key, version, ProductionProductDefinition.from_dict(definition).to_dict())
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def publish(self, key: str, version: int) -> dict[str, object]:
        versions = await self.repository.get_versions(key)
        target = next((item for item in versions if item.version == version), None)
        if target is None:
            raise LookupError("Production product version not found.")
        if target.status != "DRAFT":
            raise ValueError("Only DRAFT product versions can be published.")
        definition = ProductionProductDefinition.from_dict(target.definition)
        resolver = ControlPlaneResolver()
        references = definition.component_versions or {}

        # Preserve exact references carried by a derived/copied draft. Only
        # components deliberately changed or newly selected are resolved to the
        # active published version at this publication boundary.
        recipe = (
            await resolver.resolve_recipe_version(self.session, references["recipe"])
            if "recipe" in references else await resolver.resolve_recipe(self.session, definition.recipe_key)
        )
        output_contract = (
            await resolver.resolve_output_contract_version(self.session, references["output_contract"])
            if "output_contract" in references else
            await resolver.resolve_output_contract(self.session, definition.output_contract_key)
        )
        policy = (
            await resolver.resolve_policy_version(self.session, references["policy"])
            if "policy" in references else await resolver.resolve_policy(self.session, definition.policy_key)
        )
        contract_definition = OutputContractDefinition.from_dict(output_contract.definition)
        final_capability = recipe.stages[-1].capability_key
        capability_output_kind = {
            "produce_post": "POST",
            "produce_text_artifact": "TEXT",
            "produce_quiz_artifact": "QUIZ",
            "produce_image_artifact": "IMAGE",
            "produce_video_artifact": "VIDEO",
            "produce_audio_artifact": "AUDIO",
        }.get(final_capability)
        if capability_output_kind is None or contract_definition.artifact_kind != capability_output_kind:
            raise ValueError(
                f"Product recipe '{definition.recipe_key}' ends with capability '{final_capability}', "
                f"which is incompatible with output contract '{definition.output_contract_key}' "
                f"({contract_definition.artifact_kind})."
            )
        if contract_definition.content_mode == "STORAGE_URI":
            try:
                storage = S3ArtifactStorage.from_environment()
                await storage.ensure_available()
            except (ArtifactStorageConfigurationError, ArtifactStorageError) as exc:
                raise ValueError(
                    "Cannot publish a media product until durable ARTIFACT_STORAGE_* settings and bucket access are valid."
                ) from exc

        if not definition.prompt_key or not definition.identity_key:
            raise ValueError(
                "A new product version must explicitly select a published editorial prompt and identity before publication."
            )
        prompt = (
            await resolver.resolve_prompt_version(self.session, references["prompt"])
            if "prompt" in references else await resolver.resolve_prompt(self.session, definition.prompt_key)
        )
        identity = (
            await resolver.resolve_identity_version(self.session, references["identity"])
            if "identity" in references else await resolver.resolve_identity(self.session, definition.identity_key)
        )
        component_versions = {
            "prompt": {"key": prompt.key, "version_id": str(prompt.version_id), "version": prompt.version},
            "identity": {"key": identity.key, "version_id": identity.version_id, "version": identity.version},
            "recipe": {"key": recipe.key, "version_id": str(recipe.version_id), "version": recipe.version},
            "policy": {"key": policy.key, "version_id": policy.version_id, "version": policy.version},
            "output_contract": {
                "key": output_contract.key,
                "version_id": output_contract.version_id,
                "version": output_contract.version,
            },
        }
        target.definition = {**definition.to_dict(), "component_versions": component_versions}
        await self.session.flush()
        row = await self.repository.publish(key, version)
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def archive(self, key: str, version: int) -> dict[str, object]:
        row = await self.repository.archive(key, version)
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)
