from sqlalchemy.exc import IntegrityError

from app.domain.products import ProductionProductDefinition
from app.domain.output_contracts import OutputContractDefinition
from app.infrastructure.database.products import ProductionProductRepository
from app.infrastructure.database.recipes import ProductionRecipeRepository
from app.infrastructure.database.output_contracts import OutputContractRepository
from app.infrastructure.database.policies import ProductionPolicyRepository
from app.infrastructure.artifact_storage import ArtifactStorageConfigurationError, ArtifactStorageError, S3ArtifactStorage
from app.application.control_plane import ControlPlaneResolver


def _version_payload(row) -> dict[str, object]:
    return {
        "id": str(row.id), "product_id": str(row.product_id), "version": row.version,
        "definition": ProductionProductDefinition.from_dict(row.definition).to_dict(),
        "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _product_payload(row, versions: list | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(row.id), "key": row.key, "name": row.name, "purpose": row.purpose,
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
        return _product_payload(row, await self.repository.get_versions(key))

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

        # Validate recipe/output/policy compatibility before manifest capture.
        recipe = await resolver.resolve_recipe(self.session, definition.recipe_key)
        output_contract = await resolver.resolve_output_contract(self.session, definition.output_contract_key)
        policy = await resolver.resolve_policy(self.session, definition.policy_key)
        contract_definition = OutputContractDefinition.from_dict(output_contract.definition)
        final_capability = recipe.stages[-1].capability_key
        capability_output_kind = {
            "produce_post": "POST",
            "produce_text_artifact": "TEXT",
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
        prompt = await resolver.resolve_prompt(self.session, definition.prompt_key)
        identity = await resolver.resolve_identity(self.session, definition.identity_key)
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
