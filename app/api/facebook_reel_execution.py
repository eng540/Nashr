"""Owner exact Reel decisions. Preview alone cannot upload or publish."""
from uuid import UUID
from fastapi import APIRouter,Request,Depends,HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import FacebookReelJobModel as Job
from app.api.instagram_connections import owner,mutation_owner,HEADERS
from app.application import facebook_reel_runtime as service
from app.application.instagram_oauth import digest
router=APIRouter(prefix='/api/connections/facebook/reels',tags=['facebook-exact-reel'])
class Approval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    snapshot_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    exact_words_approved:StrictBool
    public_page_approved:StrictBool
    media_transfer_approved:StrictBool

@router.post('/materials/{uid}/preview')
async def preview(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:return JSONResponse(await service.stage(session,uid),headers=HEADERS)
    except ValueError as e:raise HTTPException(409,str(e)) from None

@router.get('/{jid}')
async def result(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    owner(request);j=await session.get(Job,jid)
    if not j:raise HTTPException(404,'محاولة غير موجودة.')
    return JSONResponse(service.describe(j),headers=HEADERS)

@router.post('/{jid}/approve')
async def approve(jid:UUID,payload:Approval,request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request)
    if any(x is not True for x in [payload.exact_words_approved,payload.public_page_approved,payload.media_transfer_approved]):raise HTTPException(409,'يلزم قرار نشر صريح على الوصف والفيديو والصفحة العامة.')
    j=(await session.execute(select(Job).where(Job.id==jid).with_for_update())).scalar_one_or_none()
    if not j:raise HTTPException(404,'محاولة غير موجودة.')
    try:return JSONResponse(await service.approve(session,j,payload.snapshot_hash,'owner-session:'+digest(token)),headers=HEADERS)
    except ValueError as e:raise HTTPException(409,str(e)) from None

@router.post('/{jid}/cancel')
async def cancel(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request);j=(await session.execute(select(Job).where(Job.id==jid).with_for_update())).scalar_one_or_none()
    if not j or j.state not in {'DRAFT','APPROVED'}:raise HTTPException(409,'لا يمكن إلغاء إرسال بدأ لدى Meta محلياً.')
    await service.claim(session,j,'CANCELLED');return JSONResponse(service.describe(j),headers=HEADERS)

@router.post('/materials/{uid}/prepare-delivery')
async def prepare_delivery(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:return JSONResponse(await service.prepare_delivery(session,uid),headers=HEADERS)
    except ValueError as e:raise HTTPException(409,str(e)) from None
