from sqlalchemy.exc import IntegrityError

from app.domain.output_contracts import OutputContractDefinition
from app.infrastructure.database.output_contracts import OutputContractRepository


def _version_payload(row) -> dict[str, object]:
    return {
        "id": str(row.id),
        "contract_id": str(row.contract_id),
        "version": row.version,
        "definition": OutputContractDefinition.from_dict(row.definition).to_dict(),
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _contract_payload(row, versions: list | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(row.id),
        "key": row.key,
        "name": row.name,
        "purpose": row.purpose,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if versions is not None:
        payload["versions"] = [_version_payload(version) for version in versions]
        payload["active_version"] = next(
            (version.version for version in versions if version.status == "PUBLISHED"), None
        )
    return payload


class OutputContractControlPlaneService:
    def __init__(self, session) -> None:
        self.repository = OutputContractRepository(session)
        self.session = session

    async def list_contracts(self) -> list[dict[str, object]]:
        rows = await self.repository.list_contracts()
        return [
            _contract_payload(row, await self.repository.get_versions(row.key))
            for row in rows
        ]

    async def get_contract(self, key: str) -> dict[str, object]:
        row = await self.repository.get_contract(key)
        if row is None:
            raise LookupError("Output contract not found.")
        return _contract_payload(row, await self.repository.get_versions(key))

    async def create_contract(self, key: str, name: str, purpose: str, definition: dict[str, object]) -> dict[str, object]:
        definition = OutputContractDefinition.from_dict(definition).to_dict()
        if not name.strip() or not purpose.strip():
            raise ValueError("Output contract name and purpose are required.")
        if await self.repository.get_contract(key):
            raise ValueError("Output contract key already exists.")
        try:
            row, version = await self.repository.create_contract(key.strip(), name.strip(), purpose.strip(), definition)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Output contract key already exists.") from exc
        await self.session.refresh(row)
        await self.session.refresh(version)
        return {**_contract_payload(row), "created_version": _version_payload(version)}

    async def create_draft(self, key: str, definition: dict[str, object]) -> dict[str, object]:
        definition = OutputContractDefinition.from_dict(definition).to_dict()
        row = await self.repository.create_draft(key, definition)
        await self.session.commit()
        await self.session.refresh(row)
        return _version_payload(row)

    async def update_draft(self, key: str, version: int, definition: dict[str, object]) -> dict[str, object]:
        definition = OutputContractDefinition.from_dict(definition).to_dict()
        row = await self.repository.update_draft(key, version, definition)
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
