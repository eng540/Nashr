"""Owner-only internal agent plans, explicit bounded action execution."""
from uuid import UUID
from fastapi import APIRouter,Request,Depends,HTTPException
from fastapi.responses import JSONResponse,HTMLResponse
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.instagram_connections import owner,mutation_owner,HEADERS
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import NashrAgentTaskModel as Task,ArtifactModel as Artifact
from app.application import nashr_agent as flow
from app.api.frontend import frontend_index_response
router=APIRouter()
class Preview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_text:str=Field(min_length=1,max_length=2000)
    action:str
    artifact_ids:list[UUID]=Field(min_length=1,max_length=20)
class Create(Preview):
    plan_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:str=Field(pattern=r'^[A-Za-z0-9_.:-]{8,100}$')
@router.get('/agent',include_in_schema=False)
async def page():return frontend_index_response() or HTMLResponse('<h1>مساحة الوكيل تحتاج بناء الواجهة.</h1>')
@router.get('/api/agent/materials')
async def materials(request:Request,session:AsyncSession=Depends(get_session)):
    owner(request)
    rows=await session.scalars(select(Artifact).where(Artifact.kind!='POST').order_by(Artifact.created_at.desc()).limit(100))
    return JSONResponse(dict(items=[dict(id=str(a.id),kind=a.kind,label=(a.content or (a.artifact_metadata or {}).get('caption') or str(a.id))[:100],review_status=a.review_status)for a in rows if (a.artifact_metadata or {}).get('source_type')!='PLATFORM_VARIANT']),headers=HEADERS)
@router.post('/api/agent/preview')
async def preview(payload:Preview,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:r=await flow.preview(session,**payload.model_dump())
    except ValueError as e:raise HTTPException(409,str(e))from None
    return JSONResponse(r,headers=HEADERS)
@router.post('/api/agent/tasks')
async def create(payload:Create,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:r=await flow.create(session,**payload.model_dump())
    except ValueError as e:raise HTTPException(409,str(e))from None
    return JSONResponse(r,headers=HEADERS)
@router.get('/api/agent/tasks')
async def history(request:Request,session:AsyncSession=Depends(get_session)):
    owner(request);rows=await session.scalars(select(Task).order_by(Task.created_at.desc()).limit(50))
    return JSONResponse(dict(items=[flow.describe(t)for t in rows]),headers=HEADERS)
@router.post('/api/agent/tasks/{uid}/{command}')
async def command(uid:UUID,command:str,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:r=await flow.command(session,uid,command)
    except LookupError as e:raise HTTPException(404,str(e))from None
    except ValueError as e:raise HTTPException(409,str(e))from None
    return JSONResponse(r,headers=HEADERS)
