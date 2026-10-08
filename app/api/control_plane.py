from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.control_plane import PromptTemplateService
from app.infrastructure.database.session import get_session


router = APIRouter(prefix="/api/control", tags=["control-plane"])


class PromptTemplateCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    body: str = Field(min_length=1, max_length=200000)


class PromptVersionRequest(BaseModel):
    body: str = Field(min_length=1, max_length=200000)


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
