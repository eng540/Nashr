from sqlalchemy.exc import IntegrityError

from app.domain.policies import ProductionPolicyDefinition
from app.infrastructure.database.policies import ProductionPolicyRepository


def _version_payload(row) -> dict[str, object]:
    return {
        "id": str(row.id), "policy_id": str(row.policy_id), "version": row.version,
        "definition": ProductionPolicyDefinition.from_dict(row.definition).to_dict(),
        "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _policy_payload(row, versions: list | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(row.id), "key": row.key, "name": row.name, "purpose": row.purpose,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }
    if versions is not None:
        payload["versions"] = [_version_payload(version) for version in versions]
        payload["active_version"] = next((version.version for version in versions if version.status == "PUBLISHED"), None)
    return payload


class ProductionPolicyControlPlaneService:
    def __init__(self, session) -> None:
        self.repository = ProductionPolicyRepository(session)
        self.session = session

    async def list_policies(self) -> list[dict[str, object]]:
        rows = await self.repository.list_policies()
        return [_policy_payload(row, await self.repository.get_versions(row.key)) for row in rows]

    async def get_policy(self, key: str) -> dict[str, object]:
        row = await self.repository.get_policy(key)
        if row is None:
            raise LookupError("Production policy not found.")
        return _policy_payload(row, await self.repository.get_versions(key))

    async def create_policy(self, key: str, name: str, purpose: str, definition: dict[str, object]) -> dict[str, object]:
        definition = ProductionPolicyDefinition.from_dict(definition).to_dict()
        if not name.strip() or not purpose.strip():
            raise ValueError("Production policy name and purpose are required.")
        if await self.repository.get_policy(key):
            raise ValueError("Production policy key already exists.")
        try:
            row, version = await self.repository.create_policy(key.strip(), name.strip(), purpose.strip(), definition)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Production policy key already exists.") from exc
        await self.session.refresh(row)
        await self.session.refresh(version)
        return {**_policy_payload(row), "created_version": _version_payload(version)}

    async def create_draft(self, key: str, definition: dict[str, object]) -> dict[str, object]:
        row = await self.repository.create_draft(key, ProductionPolicyDefinition.from_dict(definition).to_dict())
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def update_draft(self, key: str, version: int, definition: dict[str, object]) -> dict[str, object]:
        row = await self.repository.update_draft(key, version, ProductionPolicyDefinition.from_dict(definition).to_dict())
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def publish(self, key: str, version: int) -> dict[str, object]:
        row = await self.repository.publish(key, version)
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def archive(self, key: str, version: int) -> dict[str, object]:
        row = await self.repository.archive(key, version)
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)
