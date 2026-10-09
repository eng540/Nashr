from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.control_plane import PromptTemplateService
from app.application.recipe_control_plane import ProductionRecipeControlPlaneService
from app.infrastructure.database.session import get_session


router = APIRouter(prefix="/api/control", tags=["control-plane"])


class PromptTemplateCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    body: str = Field(min_length=1, max_length=200000)


class PromptVersionRequest(BaseModel):
    body: str = Field(min_length=1, max_length=200000)



class RecipeStageRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9._-]+$")
    capability_key: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9._-]+$")
    capability_version: int = Field(ge=1)


class RecipeCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    stages: list[RecipeStageRequest] = Field(min_length=1, max_length=50)


class RecipeStagesRequest(BaseModel):
    stages: list[RecipeStageRequest] = Field(min_length=1, max_length=50)


def _recipe_stages(payload: RecipeStagesRequest | RecipeCreateRequest) -> list[dict[str, Any]]:
    return [stage.model_dump() for stage in payload.stages]


def _version_payload(version) -> dict[str, Any]:
    return {
        "version": version.version,
        "body": version.body,
        "status": version.status,
        "created_at": version.created_at,
        "updated_at": version.updated_at,
    }


def _template_payload(template, versions=None) -> dict[str, Any]:
    payload = {
        "key": template.key,
        "name": template.name,
        "purpose": template.purpose,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }
    if versions is not None:
        payload["versions"] = [_version_payload(version) for version in versions]
        payload["active_version"] = next(
            (version.version for version in versions if version.status == "PUBLISHED"),
            None,
        )
    return payload


@router.get("/prompts")
async def list_prompts(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return [_template_payload(template) for template in await PromptTemplateService(session).list_templates()]


@router.get("/prompts/{key}")
async def get_prompt(key: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        template, versions = await PromptTemplateService(session).get_template(key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _template_payload(template, versions)


@router.post("/prompts", status_code=201)
async def create_prompt(payload: PromptTemplateCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        template, version = await PromptTemplateService(session).create_template(
            payload.key, payload.name, payload.purpose, payload.body
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {**_template_payload(template), "created_version": _version_payload(version)}


@router.post("/prompts/{key}/versions", status_code=201)
async def create_prompt_version(key: str, payload: PromptVersionRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return _version_payload(await PromptTemplateService(session).create_draft(key, payload.body))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/prompts/{key}/versions/{version}")
async def update_prompt_version(key: str, version: int, payload: PromptVersionRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return _version_payload(await PromptTemplateService(session).update_draft(key, version, payload.body))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/prompts/{key}/versions/{version}/publish")
async def publish_prompt_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return _version_payload(await PromptTemplateService(session).publish(key, version))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/prompts/{key}/versions/{version}/archive")
async def archive_prompt_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return _version_payload(await PromptTemplateService(session).archive(key, version))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/recipes")
async def list_recipes(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await ProductionRecipeControlPlaneService(session).list_recipes()


@router.get("/recipes/{key}")
async def get_recipe(key: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionRecipeControlPlaneService(session).get_recipe(key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/recipes", status_code=201)
async def create_recipe(payload: RecipeCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionRecipeControlPlaneService(session).create_recipe(
            payload.key, payload.name, payload.purpose, _recipe_stages(payload)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/recipes/{key}/versions", status_code=201)
async def create_recipe_version(key: str, payload: RecipeStagesRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionRecipeControlPlaneService(session).create_draft(key, _recipe_stages(payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/recipes/{key}/versions/{version}")
async def update_recipe_version(key: str, version: int, payload: RecipeStagesRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionRecipeControlPlaneService(session).update_draft(key, version, _recipe_stages(payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/recipes/{key}/versions/{version}/publish")
async def publish_recipe_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionRecipeControlPlaneService(session).publish(key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/recipes/{key}/versions/{version}/archive")
async def archive_recipe_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionRecipeControlPlaneService(session).archive(key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
