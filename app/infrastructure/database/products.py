from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ProductionProductModel, ProductionProductVersionModel


class ProductionProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_products(self) -> list[ProductionProductModel]:
        result = await self.session.execute(select(ProductionProductModel).order_by(ProductionProductModel.key.asc()))
        return list(result.scalars().all())

    async def get_product(self, key: str, *, for_update: bool = False) -> ProductionProductModel | None:
        statement = select(ProductionProductModel).where(ProductionProductModel.key == key)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_versions(self, key: str) -> list[ProductionProductVersionModel]:
        result = await self.session.execute(
            select(ProductionProductVersionModel).join(ProductionProductModel)
            .where(ProductionProductModel.key == key)
            .order_by(ProductionProductVersionModel.version.desc())
        )
        return list(result.scalars().all())

    async def resolve_active(self, key: str) -> tuple[ProductionProductModel, ProductionProductVersionModel]:
        result = await self.session.execute(
            select(ProductionProductModel, ProductionProductVersionModel)
            .join(ProductionProductVersionModel, ProductionProductVersionModel.product_id == ProductionProductModel.id)
            .where(ProductionProductModel.key == key, ProductionProductVersionModel.status == "PUBLISHED")
        )
        row = result.one_or_none()
        if row is None:
            raise LookupError(f"No active published product exists for key '{key}'.")
        return row

    async def create_product(self, key: str, name: str, purpose: str, definition: dict[str, object]):
        product = ProductionProductModel(id=uuid4(), key=key, name=name, purpose=purpose)
        self.session.add(product)
        await self.session.flush()
        version = ProductionProductVersionModel(
            id=uuid4(), product_id=product.id, version=1, definition=definition, status="DRAFT"
        )
        self.session.add(version)
        await self.session.flush()
        return product, version

    async def create_draft(self, key: str, definition: dict[str, object]) -> ProductionProductVersionModel:
        product = await self.get_product(key, for_update=True)
        if product is None:
            raise LookupError("Production product not found.")
        latest = (await self.session.execute(
            select(func.max(ProductionProductVersionModel.version)).where(
                ProductionProductVersionModel.product_id == product.id
            )
        )).scalar_one()
        row = ProductionProductVersionModel(
            id=uuid4(), product_id=product.id, version=(latest or 0) + 1,
            definition=definition, status="DRAFT",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_draft(self, key: str, version: int, definition: dict[str, object]) -> ProductionProductVersionModel:
        if await self.get_product(key, for_update=True) is None:
            raise LookupError("Production product not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Production product version not found.")
        if row.status != "DRAFT":
            raise ValueError("Only DRAFT product versions can be edited.")
        row.definition = definition
        await self.session.flush()
        return row

    async def publish(self, key: str, version: int) -> ProductionProductVersionModel:
        product = await self.get_product(key, for_update=True)
        if product is None:
            raise LookupError("Production product not found.")
        target = await self._get_version_row(key, version)
        if target is None:
            raise LookupError("Production product version not found.")
        if target.status != "DRAFT":
            raise ValueError("Only DRAFT product versions can be published.")
        await self.session.execute(
            update(ProductionProductVersionModel)
            .where(ProductionProductVersionModel.product_id == product.id, ProductionProductVersionModel.status == "PUBLISHED")
            .values(status="ARCHIVED")
        )
        target.status = "PUBLISHED"
        await self.session.flush()
        return target

    async def archive(self, key: str, version: int) -> ProductionProductVersionModel:
        if await self.get_product(key, for_update=True) is None:
            raise LookupError("Production product not found.")
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Production product version not found.")
        if row.status == "PUBLISHED":
            raise ValueError("The active PUBLISHED product cannot be archived directly.")
        if row.status == "ARCHIVED":
            return row
        row.status = "ARCHIVED"
        await self.session.flush()
        return row

    async def _get_version_row(self, key: str, version: int) -> ProductionProductVersionModel | None:
        result = await self.session.execute(
            select(ProductionProductVersionModel).join(ProductionProductModel)
            .where(ProductionProductModel.key == key, ProductionProductVersionModel.version == version)
        )
        return result.scalar_one_or_none()
