from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.policy_control_plane import ProductionPolicyControlPlaneService
from app.infrastructure.database.session import get_session


router = APIRouter(prefix="/api/control/policies", tags=["production-policy-control-plane"])


class PolicyDefinitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_content_chars: int = Field(default=1, ge=0, strict=True)
    max_content_chars: int = Field(default=100000, ge=1, strict=True)
    required_terms: list[str] = Field(default_factory=list, max_length=100)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=100)
    allow_urls: bool = True


class PolicyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    definition: PolicyDefinitionRequest


class PolicyVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: PolicyDefinitionRequest


def _definition(payload: PolicyDefinitionRequest) -> dict[str, Any]:
    return payload.model_dump()


@router.get("")
async def list_policies(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await ProductionPolicyControlPlaneService(session).list_policies()


@router.get("/{key}")
async def get_policy(key: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionPolicyControlPlaneService(session).get_policy(key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", status_code=201)
async def create_policy(payload: PolicyCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionPolicyControlPlaneService(session).create_policy(payload.key, payload.name, payload.purpose, _definition(payload.definition))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{key}/versions", status_code=201)
async def create_policy_version(key: str, payload: PolicyVersionRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionPolicyControlPlaneService(session).create_draft(key, _definition(payload.definition))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{key}/versions/{version}")
async def update_policy_version(key: str, version: int, payload: PolicyVersionRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionPolicyControlPlaneService(session).update_draft(key, version, _definition(payload.definition))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{key}/versions/{version}/publish")
async def publish_policy_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionPolicyControlPlaneService(session).publish(key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{key}/versions/{version}/archive")
async def archive_policy_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionPolicyControlPlaneService(session).archive(key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
