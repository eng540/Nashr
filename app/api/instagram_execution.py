"""Authenticated exact publication decisions and capability-only media delivery."""
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter,Request,Depends,HTTPException
from fastapi.responses import JSONResponse,Response
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import InstagramExecutionModel as Job,InstagramDispatchModel as Dispatch
from app.api.instagram_connections import owner,mutation_owner,HEADERS
from app.application import instagram_publish_decisions as decisions,instagram_dispatch as dispatch,instagram_media_grants as grants,instagram_unified_execution as execution
router=APIRouter()
BASE='/api/connections/instagram/materials/{uid}/execution-drafts/{jid}'

async def selected(session,uid,jid):
    job=await session.get(Job,jid,populate_existing=True)
    if not job or job.artifact_id!=uid or job.connection_binding.get('login_mode')!='UNIFIED':raise HTTPException(404,'مسودة Unified غير موجودة لهذه المادة.')
    return job

class Proposal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    due_at:datetime
    timezone_name:str=Field(max_length=100)

class Approval(Proposal):
    decision_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    exact_words_approved:StrictBool
    public_post_approved:StrictBool
    media_disclosure_approved:StrictBool

@router.post(BASE+'/proposal')
async def proposal(uid:UUID,jid:UUID,payload:Proposal,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request);await selected(session,uid,jid)
    try:result=await decisions.proposal(session,jid,**payload.model_dump())
    except (ValueError,KeyError):raise HTTPException(409,'تغيرت المسودة أو الربط؛ راجع المعاينة أولاً.') from None
    return JSONResponse(result,headers=HEADERS)

@router.post(BASE+'/approve')
async def approve(uid:UUID,jid:UUID,payload:Approval,request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request);await selected(session,uid,jid)
    # Deployment origin validated before recording any runnable dispatch.
    from app.application.instagram_runtime import public_origin
    try:
        public_origin()
        from app.application.instagram_oauth import digest
        decision=await decisions.record(session,jid,**payload.model_dump(),evidence_ref='owner-session:'+digest(token),authenticated_owner=True)
        row=await dispatch.schedule(session,jid,decision.id)
    except (ValueError,KeyError):raise HTTPException(409,'لم تسجل خطة تنفيذ؛ راجع القرار والوقت والربط.') from None
    return JSONResponse({'dispatch_id':str(row.id),'decision_id':str(decision.id),'state':row.state,'due_at':row.due_at.isoformat()},headers=HEADERS)

@router.get(BASE+'/result')
async def result(uid:UUID,jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    owner(request);job=await selected(session,uid,jid)
    return JSONResponse(await execution.describe_result(session,job),headers=HEADERS)

@router.post(BASE+'/revoke')
async def revoke(uid:UUID,jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request);await selected(session,uid,jid)
    row=(await session.execute(select(Dispatch).where(Dispatch.execution_id==jid))).scalar_one_or_none()
    if not row:raise HTTPException(404,'لا قرار نشر لهذه المسودة.')
    try:receipt=await decisions.revoke(session,row.decision_id)
    except ValueError:raise HTTPException(409,'تعذر تأكيد الإيقاف؛ أعد قراءة النتيجة.') from None
    return JSONResponse({'revoked':True,'already_published_content_removed':False,'stop_receipt':receipt},headers=HEADERS)

@router.get('/instagram-media',include_in_schema=False)
async def media(request:Request,session:AsyncSession=Depends(get_session)):
    # Auth middleware captures then strips this credential before access logging.
    capability=getattr(request.state,'instagram_media_capability','')
    try:content,mime=await grants.read(session,capability)
    except Exception:raise HTTPException(404,'Media unavailable') from None
    return Response(content,media_type=mime,headers={**HEADERS,'Content-Disposition':'inline','Accept-Ranges':'none'})
