"""Owner-only private batch reviews. No execution approval route."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.instagram_connections import owner, mutation_owner, HEADERS
from app.infrastructure.database.session import get_session
from app.application import instagram_batch_review as flow
router=APIRouter(prefix='/api/connections/instagram/batch-reviews',tags=['instagram-private-batch-review'])

class Entry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    artifact_id:UUID
    due_at:datetime
    timezone:str=Field(min_length=1,max_length=100)
    share_to_feed:StrictBool|None

class Preview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items:list[Entry]=Field(min_length=1,max_length=20)

class Save(Preview):
    preview_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:str=Field(pattern=r'^[A-Za-z0-9_.:-]{8,100}$')

def values(payload):return [i.model_dump() for i in payload.items]

@router.post('/preview')
async def preview(payload:Preview,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:result=await flow.preview(session,values(payload))
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

@router.post('')
async def save(payload:Save,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:result=await flow.save(session,values(payload),preview_hash=payload.preview_hash,request_key=payload.request_key)
    except (ValueError,DBAPIError) as exc:
        await session.rollback()
        raise HTTPException(409,str(exc) if isinstance(exc,ValueError) else 'تغيرت الدفعة أثناء الحفظ. حدّث القراءة؛ لم نحفظ جزءاً منها.') from None
    return JSONResponse(result,headers=HEADERS)

@router.get('')
async def history(request:Request,session:AsyncSession=Depends(get_session)):
    owner(request)
    return JSONResponse(await flow.history(session),headers=HEADERS)

@router.get('/{uid}')
async def get_review(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    owner(request)
    try:result=await flow.get_review(session,uid)
    except ValueError as exc:raise HTTPException(404,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

@router.post('/{uid}/cancel')
async def cancel(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:result=await flow.cancel(session,uid)
    except ValueError as exc:raise HTTPException(404,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)
