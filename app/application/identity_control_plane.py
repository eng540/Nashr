from sqlalchemy.exc import IntegrityError

from app.domain.identities import EditorialIdentityDefinition
from app.infrastructure.database.identities import EditorialIdentityRepository


def _version_payload(row) -> dict[str, object]:
    return {
        "id": str(row.id),
        "identity_id": str(row.identity_id),
        "version": row.version,
        "definition": EditorialIdentityDefinition.from_dict(row.definition).to_dict(),
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _identity_payload(row, versions: list | None = None) -> dict[str, object]:
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
            (version.version for version in versions if version.status == "PUBLISHED"),
            None,
        )
    return payload


class EditorialIdentityControlPlaneService:
    def __init__(self, session) -> None:
        self.repository = EditorialIdentityRepository(session)
        self.session = session

    async def list_identities(self) -> list[dict[str, object]]:
        identities = await self.repository.list_identities()
        return [
            _identity_payload(identity, await self.repository.get_versions(identity.key))
            for identity in identities
        ]

    async def get_identity(self, key: str) -> dict[str, object]:
        identity = await self.repository.get_identity(key)
        if identity is None:
            raise LookupError("Editorial identity not found.")
        return _identity_payload(identity, await self.repository.get_versions(key))

    async def create_identity(
        self, key: str, name: str, purpose: str, definition: dict[str, object]
    ) -> dict[str, object]:
        definition = EditorialIdentityDefinition.from_dict(definition).to_dict()
        if not name.strip() or not purpose.strip():
            raise ValueError("Editorial identity name and purpose are required.")
        if await self.repository.get_identity(key):
            raise ValueError("Editorial identity key already exists.")
        try:
            identity, version = await self.repository.create_identity(
                key.strip(), name.strip(), purpose.strip(), definition
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("Editorial identity key already exists.") from exc
        await self.session.refresh(identity)
        await self.session.refresh(version)
        return {**_identity_payload(identity), "created_version": _version_payload(version)}

    async def create_draft(self, key: str, definition: dict[str, object]) -> dict[str, object]:
        definition = EditorialIdentityDefinition.from_dict(definition).to_dict()
        result = await self.repository.create_draft(key, definition)
        await self.session.commit()
        await self.session.refresh(result)
        return _version_payload(result)

    async def update_draft(
        self, key: str, version: int, definition: dict[str, object]
    ) -> dict[str, object]:
        definition = EditorialIdentityDefinition.from_dict(definition).to_dict()
        result = await self.repository.update_draft(key, version, definition)
        await self.session.commit()
        await self.session.refresh(result)
        return _version_payload(result)

    async def publish(self, key: str, version: int) -> dict[str, object]:
        result = await self.repository.publish(key, version)
        await self.session.commit()
        await self.session.refresh(result)
        return _version_payload(result)

    async def archive(self, key: str, version: int) -> dict[str, object]:
        result = await self.repository.archive(key, version)
        await self.session.commit()
        await self.session.refresh(result)
        return _version_payload(result)
