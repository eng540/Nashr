from sqlalchemy.exc import IntegrityError

from app.domain.products import ProductionProductDefinition
from app.infrastructure.database.products import ProductionProductRepository
from app.infrastructure.database.recipes import ProductionRecipeRepository
from app.infrastructure.database.output_contracts import OutputContractRepository
from app.infrastructure.database.policies import ProductionPolicyRepository
from app.domain.output_contracts import OutputContractDefinition
from app.infrastructure.storage import object_storage_is_configured


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
        await ProductionRecipeRepository(self.session).resolve_active(definition.recipe_key)
        _, contract_version = await OutputContractRepository(self.session).resolve_active(definition.output_contract_key)
        contract = OutputContractDefinition.from_dict(contract_version.definition)
        if contract.content_mode == "STORAGE_URI" and not object_storage_is_configured():
            raise ValueError("Durable object storage must be configured before publishing a storage-backed Product.")
        await ProductionPolicyRepository(self.session).resolve_active(definition.policy_key)
        row = await self.repository.publish(key, version)
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def archive(self, key: str, version: int) -> dict[str, object]:
        row = await self.repository.archive(key, version)
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)
