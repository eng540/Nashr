from app.domain.recipes import ProductionRecipe, RecipeStage, SUPPORTED_RECIPE_CAPABILITIES
from app.infrastructure.database.recipes import ProductionRecipeRepository


def _validate_stages(key: str, version: int, stages: list[dict[str, object]]) -> list[dict[str, object]]:
    recipe = ProductionRecipe(
        key=key,
        version=version,
        stages=tuple(RecipeStage.from_dict(stage) for stage in stages),
    )
    for stage in recipe.stages:
        if (stage.capability_key, stage.capability_version) not in SUPPORTED_RECIPE_CAPABILITIES:
            raise ValueError(
                f"Unsupported capability '{stage.capability_key}' v{stage.capability_version}."
            )
    return [stage.to_dict() for stage in recipe.stages]


def _version_payload(row) -> dict[str, object]:
    return {
        "id": str(row.id),
        "recipe_id": str(row.recipe_id),
        "version": row.version,
        "stages": row.definition["stages"],
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _recipe_payload(row, versions: list | None = None) -> dict[str, object]:
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


class ProductionRecipeControlPlaneService:
    def __init__(self, session) -> None:
        self.repository = ProductionRecipeRepository(session)
        self.session = session

    async def list_recipes(self) -> list[dict[str, object]]:
        recipes = await self.repository.list_recipes()
        return [
            _recipe_payload(recipe, await self.repository.get_versions(recipe.key))
            for recipe in recipes
        ]

    async def get_recipe(self, key: str) -> dict[str, object]:
        recipe = await self.repository.get_recipe(key)
        if recipe is None:
            raise LookupError("Production recipe not found.")
        return _recipe_payload(recipe, await self.repository.get_versions(key))

    async def create_recipe(
        self, key: str, name: str, purpose: str, stages: list[dict[str, object]]
    ) -> dict[str, object]:
        stages = _validate_stages(key, 1, stages)
        if await self.repository.get_recipe(key):
            raise ValueError("Production recipe key already exists.")
        recipe, version = await self.repository.create_recipe(key, name.strip(), purpose.strip(), stages)
        await self.session.commit()
        return {**_recipe_payload(recipe), "created_version": _version_payload(version)}

    async def create_draft(self, key: str, stages: list[dict[str, object]]) -> dict[str, object]:
        stages = _validate_stages(key, 1, stages)
        version = await self.repository.create_draft(key, stages)
        await self.session.commit()
        return _version_payload(version)

    async def update_draft(self, key: str, version: int, stages: list[dict[str, object]]) -> dict[str, object]:
        stages = _validate_stages(key, version, stages)
        result = await self.repository.update_draft(key, version, stages)
        await self.session.commit()
        return _version_payload(result)

    async def publish(self, key: str, version: int) -> dict[str, object]:
        result = await self.repository.publish(key, version)
        await self.session.commit()
        return _version_payload(result)

    async def archive(self, key: str, version: int) -> dict[str, object]:
        result = await self.repository.archive(key, version)
        await self.session.commit()
        return _version_payload(result)
