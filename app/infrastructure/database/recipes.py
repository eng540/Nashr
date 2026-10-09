from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.recipes import ProductionRecipe, RecipeStage
from app.infrastructure.database.models import ProductionRecipeModel, ProductionRecipeVersionModel


class ProductionRecipeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_recipes(self) -> list[ProductionRecipeModel]:
        result = await self.session.execute(
            select(ProductionRecipeModel).order_by(ProductionRecipeModel.key.asc())
        )
        return list(result.scalars().all())

    async def get_recipe(self, key: str) -> ProductionRecipeModel | None:
        result = await self.session.execute(
            select(ProductionRecipeModel).where(ProductionRecipeModel.key == key)
        )
        return result.scalar_one_or_none()

    async def get_versions(self, key: str) -> list[ProductionRecipeVersionModel]:
        result = await self.session.execute(
            select(ProductionRecipeVersionModel)
            .join(ProductionRecipeModel)
            .where(ProductionRecipeModel.key == key)
            .order_by(ProductionRecipeVersionModel.version.desc())
        )
        return list(result.scalars().all())

    async def resolve_active(self, key: str) -> ProductionRecipe:
        result = await self.session.execute(
            select(ProductionRecipeModel, ProductionRecipeVersionModel)
            .join(
                ProductionRecipeVersionModel,
                ProductionRecipeVersionModel.recipe_id == ProductionRecipeModel.id,
            )
            .where(
                ProductionRecipeModel.key == key,
                ProductionRecipeVersionModel.status == "PUBLISHED",
            )
        )
        row = result.one_or_none()
        if row is None:
            raise LookupError(f"No active published recipe exists for key '{key}'.")
        recipe, version = row
        stages = version.definition.get("stages")
        if not isinstance(stages, list):
            raise ValueError(f"Published recipe '{key}' v{version.version} has an invalid definition.")
        return ProductionRecipe(
            key=recipe.key,
            version=version.version,
            stages=tuple(RecipeStage.from_dict(stage) for stage in stages),
            recipe_id=str(recipe.id),
            version_id=str(version.id),
        )

    async def create_recipe(
        self,
        key: str,
        name: str,
        purpose: str,
        stages: list[dict[str, object]],
    ) -> tuple[ProductionRecipeModel, ProductionRecipeVersionModel]:
        recipe = ProductionRecipeModel(
            id=uuid4(),
            key=key,
            name=name,
            purpose=purpose,
        )
        self.session.add(recipe)
        await self.session.flush()
        version = ProductionRecipeVersionModel(
            id=uuid4(),
            recipe_id=recipe.id,
            version=1,
            definition={"stages": stages},
            status="DRAFT",
        )
        self.session.add(version)
        await self.session.flush()
        return recipe, version

    async def create_draft(
        self,
        key: str,
        stages: list[dict[str, object]],
    ) -> ProductionRecipeVersionModel:
        recipe = await self.get_recipe(key)
        if recipe is None:
            raise LookupError("Production recipe not found.")
        latest = (
            await self.session.execute(
                select(func.max(ProductionRecipeVersionModel.version)).where(
                    ProductionRecipeVersionModel.recipe_id == recipe.id
                )
            )
        ).scalar_one()
        version = ProductionRecipeVersionModel(
            id=uuid4(),
            recipe_id=recipe.id,
            version=(latest or 0) + 1,
            definition={"stages": stages},
            status="DRAFT",
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def update_draft(
        self,
        key: str,
        version: int,
        stages: list[dict[str, object]],
    ) -> ProductionRecipeVersionModel:
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Production recipe version not found.")
        if row.status != "DRAFT":
            raise ValueError("Only DRAFT recipe versions can be edited.")
        row.definition = {"stages": stages}
        await self.session.flush()
        return row

    async def publish(self, key: str, version: int) -> ProductionRecipeVersionModel:
        target = await self._get_version_row(key, version)
        if target is None:
            raise LookupError("Production recipe version not found.")
        if target.status != "DRAFT":
            raise ValueError("Only DRAFT recipe versions can be published.")
        recipe = await self.get_recipe(key)
        if recipe is None:
            raise LookupError("Production recipe not found.")
        await self.session.execute(
            update(ProductionRecipeVersionModel)
            .where(
                ProductionRecipeVersionModel.recipe_id == recipe.id,
                ProductionRecipeVersionModel.status == "PUBLISHED",
            )
            .values(status="ARCHIVED")
        )
        target.status = "PUBLISHED"
        await self.session.flush()
        return target

    async def archive(self, key: str, version: int) -> ProductionRecipeVersionModel:
        row = await self._get_version_row(key, version)
        if row is None:
            raise LookupError("Production recipe version not found.")
        if row.status == "PUBLISHED":
            raise ValueError("The active PUBLISHED recipe version cannot be archived directly.")
        if row.status == "ARCHIVED":
            return row
        row.status = "ARCHIVED"
        await self.session.flush()
        return row

    async def _get_version_row(self, key: str, version: int) -> ProductionRecipeVersionModel | None:
        result = await self.session.execute(
            select(ProductionRecipeVersionModel)
            .join(ProductionRecipeModel)
            .where(
                ProductionRecipeModel.key == key,
                ProductionRecipeVersionModel.version == version,
            )
        )
        return result.scalar_one_or_none()
