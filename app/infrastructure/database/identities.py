from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identities import EditorialIdentityDefinition
from app.infrastructure.database.models import EditorialIdentityModel, EditorialIdentityVersionModel


class EditorialIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_identities(self) -> list[EditorialIdentityModel]:
        result = await self.session.execute(
            select(EditorialIdentityModel).order_by(EditorialIdentityModel.key.asc())
        )
        return list(result.scalars().all())

    async def get_identity(self, key: str, *, for_update: bool = False) -> EditorialIdentityModel | None:
        statement = select(EditorialIdentityModel).where(EditorialIdentityModel.key == key)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_versions(self, key: str) -> list[EditorialIdentityVersionModel]:
        result = await self.session.execute(
            select(EditorialIdentityVersionModel)
            .join(EditorialIdentityModel)
            .where(EditorialIdentityModel.key == key)
            .order_by(EditorialIdentityVersionModel.version.desc())
        )
        return list(result.scalars().all())

    async def create_identity(
        self, key: str, name: str, purpose: str, definition: dict[str, object]
    ) -> tuple[EditorialIdentityModel, EditorialIdentityVersionModel]:
        identity = EditorialIdentityModel(id=uuid4(), key=key, name=name, purpose=purpose)
        self.session.add(identity)
        await self.session.flush()
        version = EditorialIdentityVersionModel(
            id=uuid4(), identity_id=identity.id, version=1,
            definition=definition, status="DRAFT",
        )
        self.session.add(version)
        await self.session.flush()
        return identity, version

    async def create_draft(self, key: str, definition: dict[str, object]) -> EditorialIdentityVersionModel:
        identity = await self.get_identity(key, for_update=True)
        if identity is None:
            raise LookupError("Editorial identity not found.")
        latest = (
            await self.session.execute(
                select(func.max(EditorialIdentityVersionModel.version)).where(
                    EditorialIdentityVersionModel.identity_id == identity.id
                )
            )
        ).scalar_one()
        row = EditorialIdentityVersionModel(
            id=uuid4(), identity_id=identity.id, version=(latest or 0) + 1,
            definition=definition, status="DRAFT",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_draft(
        self, key: str, version: int, definition: dict[str, object]
    ) -> EditorialIdentityVersionModel:
        # Serialize every lifecycle mutation on the parent identity row. This
        # prevents an edit racing with publish and changing a just-published version.
        identity = await self.get_identity(key, for_update=True)
        if identity is None:
            raise LookupError("Editorial identity not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Editorial identity version not found.")
        if row.status != "DRAFT":
            raise ValueError("Only DRAFT identity versions can be edited.")
        row.definition = definition
        await self.session.flush()
        return row

    async def publish(self, key: str, version: int) -> EditorialIdentityVersionModel:
        identity = await self.get_identity(key, for_update=True)
        if identity is None:
            raise LookupError("Editorial identity not found.")
        target = await self._get_version_row(key, version)
        if target is None:
            raise LookupError("Editorial identity version not found.")
        if target.status != "DRAFT":
            raise ValueError("Only DRAFT identity versions can be published.")
        await self.session.execute(
            update(EditorialIdentityVersionModel)
            .where(
                EditorialIdentityVersionModel.identity_id == identity.id,
                EditorialIdentityVersionModel.status == "PUBLISHED",
            )
            .values(status="ARCHIVED")
        )
        target.status = "PUBLISHED"
        await self.session.flush()
        return target

    async def archive(self, key: str, version: int) -> EditorialIdentityVersionModel:
        # Use the same lock as publish/update/create_draft to serialize lifecycle transitions.
        identity = await self.get_identity(key, for_update=True)
        if identity is None:
            raise LookupError("Editorial identity not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Editorial identity version not found.")
        if row.status == "PUBLISHED":
            raise ValueError("The active PUBLISHED identity version cannot be archived directly.")
        if row.status == "ARCHIVED":
            return row
        row.status = "ARCHIVED"
        await self.session.flush()
        return row

    async def resolve_active(self, key: str) -> tuple[EditorialIdentityModel, EditorialIdentityVersionModel]:
        result = await self.session.execute(
            select(EditorialIdentityModel, EditorialIdentityVersionModel)
            .join(
                EditorialIdentityVersionModel,
                EditorialIdentityVersionModel.identity_id == EditorialIdentityModel.id,
            )
            .where(
                EditorialIdentityModel.key == key,
                EditorialIdentityVersionModel.status == "PUBLISHED",
            )
        )
        row = result.one_or_none()
        if row is None:
            raise LookupError(f"No active published editorial identity exists for key '{key}'.")
        EditorialIdentityDefinition.from_dict(row[1].definition)
        return row[0], row[1]

    async def _get_version_row(self, key: str, version: int) -> EditorialIdentityVersionModel | None:
        result = await self.session.execute(
            select(EditorialIdentityVersionModel)
            .join(EditorialIdentityModel)
            .where(
                EditorialIdentityModel.key == key,
                EditorialIdentityVersionModel.version == version,
            )
        )
        return result.scalar_one_or_none()
