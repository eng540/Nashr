from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.product_control_plane import ProductionProductControlPlaneService
from app.infrastructure.database.session import get_session


router = APIRouter(prefix="/api/control/products", tags=["production-product-control-plane"])


class ProductDefinitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z0-9._-]+$")
    output_contract_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z0-9._-]+$")
    policy_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z0-9._-]+$")
    audience: str = Field(min_length=1, max_length=2000)
    experience: str = Field(min_length=1, max_length=2000)


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    definition: ProductDefinitionRequest


class ProductVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: ProductDefinitionRequest


def _definition(payload: ProductDefinitionRequest) -> dict[str, Any]:
    return payload.model_dump()


@router.get("")
async def list_products(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await ProductionProductControlPlaneService(session).list_products()


@router.get("/{key}")
async def get_product(key: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionProductControlPlaneService(session).get_product(key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", status_code=201)
async def create_product(payload: ProductCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionProductControlPlaneService(session).create_product(
            payload.key, payload.name, payload.purpose, _definition(payload.definition)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{key}/versions", status_code=201)
async def create_product_version(key: str, payload: ProductVersionRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionProductControlPlaneService(session).create_draft(key, _definition(payload.definition))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{key}/versions/{version}")
async def update_product_version(key: str, version: int, payload: ProductVersionRequest, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionProductControlPlaneService(session).update_draft(key, version, _definition(payload.definition))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{key}/versions/{version}/publish")
async def publish_product_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionProductControlPlaneService(session).publish(key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{key}/versions/{version}/archive")
async def archive_product_version(key: str, version: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await ProductionProductControlPlaneService(session).archive(key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
