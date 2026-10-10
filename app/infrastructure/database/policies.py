from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ProductionPolicyModel, ProductionPolicyVersionModel


class ProductionPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_policies(self) -> list[ProductionPolicyModel]:
        result = await self.session.execute(select(ProductionPolicyModel).order_by(ProductionPolicyModel.key.asc()))
        return list(result.scalars().all())

    async def get_policy(self, key: str, *, for_update: bool = False) -> ProductionPolicyModel | None:
        statement = select(ProductionPolicyModel).where(ProductionPolicyModel.key == key)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_versions(self, key: str) -> list[ProductionPolicyVersionModel]:
        result = await self.session.execute(
            select(ProductionPolicyVersionModel).join(ProductionPolicyModel)
            .where(ProductionPolicyModel.key == key)
            .order_by(ProductionPolicyVersionModel.version.desc())
        )
        return list(result.scalars().all())

    async def create_policy(self, key: str, name: str, purpose: str, definition: dict[str, object]):
        policy = ProductionPolicyModel(id=uuid4(), key=key, name=name, purpose=purpose)
        self.session.add(policy)
        await self.session.flush()
        version = ProductionPolicyVersionModel(
            id=uuid4(), policy_id=policy.id, version=1, definition=definition, status="DRAFT"
        )
        self.session.add(version)
        await self.session.flush()
        return policy, version

    async def create_draft(self, key: str, definition: dict[str, object]) -> ProductionPolicyVersionModel:
        policy = await self.get_policy(key, for_update=True)
        if policy is None:
            raise LookupError("Production policy not found.")
        latest = (await self.session.execute(
            select(func.max(ProductionPolicyVersionModel.version)).where(
                ProductionPolicyVersionModel.policy_id == policy.id
            )
        )).scalar_one()
        row = ProductionPolicyVersionModel(
            id=uuid4(), policy_id=policy.id, version=(latest or 0) + 1,
            definition=definition, status="DRAFT",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_draft(self, key: str, version: int, definition: dict[str, object]) -> ProductionPolicyVersionModel:
        if await self.get_policy(key, for_update=True) is None:
            raise LookupError("Production policy not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Production policy version not found.")
        if row.status != "DRAFT":
            raise ValueError("Only DRAFT policy versions can be edited.")
        row.definition = definition
        await self.session.flush()
        return row

    async def publish(self, key: str, version: int) -> ProductionPolicyVersionModel:
        policy = await self.get_policy(key, for_update=True)
        if policy is None:
            raise LookupError("Production policy not found.")
        target = await self._get_version_row(key, version)
        if target is None:
            raise LookupError("Production policy version not found.")
        if target.status != "DRAFT":
            raise ValueError("Only DRAFT policy versions can be published.")
        await self.session.execute(
            update(ProductionPolicyVersionModel)
            .where(ProductionPolicyVersionModel.policy_id == policy.id, ProductionPolicyVersionModel.status == "PUBLISHED")
            .values(status="ARCHIVED")
        )
        target.status = "PUBLISHED"
        await self.session.flush()
        return target

    async def archive(self, key: str, version: int) -> ProductionPolicyVersionModel:
        if await self.get_policy(key, for_update=True) is None:
            raise LookupError("Production policy not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Production policy version not found.")
        if row.status == "PUBLISHED":
            raise ValueError("The active PUBLISHED policy cannot be archived directly.")
        if row.status == "ARCHIVED":
            return row
        row.status = "ARCHIVED"
        await self.session.flush()
        return row

    async def resolve_active(self, key: str) -> tuple[ProductionPolicyModel, ProductionPolicyVersionModel]:
        result = await self.session.execute(
            select(ProductionPolicyModel, ProductionPolicyVersionModel)
            .join(ProductionPolicyVersionModel, ProductionPolicyVersionModel.policy_id == ProductionPolicyModel.id)
            .where(ProductionPolicyModel.key == key, ProductionPolicyVersionModel.status == "PUBLISHED")
        )
        row = result.one_or_none()
        if row is None:
            raise LookupError(f"No active published production policy exists for key '{key}'.")
        return row

    async def resolve_active(self, key: str) -> tuple[ProductionPolicyModel, ProductionPolicyVersionModel]:
        result = await self.session.execute(
            select(ProductionPolicyModel, ProductionPolicyVersionModel)
            .join(ProductionPolicyVersionModel, ProductionPolicyVersionModel.policy_id == ProductionPolicyModel.id)
            .where(ProductionPolicyModel.key == key, ProductionPolicyVersionModel.status == "PUBLISHED")
        )
        row = result.one_or_none()
        if row is None:
            raise LookupError(f"No active published production policy exists for key '{key}'.")
        return row

    async def _get_version_row(self, key: str, version: int) -> ProductionPolicyVersionModel | None:
        result = await self.session.execute(
            select(ProductionPolicyVersionModel).join(ProductionPolicyModel)
            .where(ProductionPolicyModel.key == key, ProductionPolicyVersionModel.version == version)
        )
        return result.scalar_one_or_none()
