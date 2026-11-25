"""Owner exact Reel decisions. Preview alone cannot upload or publish."""
from uuid import UUID
from datetime import datetime
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
class PreviewTime(BaseModel):
    model_config=ConfigDict(extra='forbid')
    due_at:datetime|None=None
    timezone_name:str|None=Field(default=None,max_length=100)

class Approval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    snapshot_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    exact_words_approved:StrictBool
    public_page_approved:StrictBool
    media_transfer_approved:StrictBool

@router.post('/materials/{uid}/preview')
async def preview(uid:UUID,request:Request,payload:PreviewTime=PreviewTime(),session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:return JSONResponse(await service.stage(session,uid,**payload.model_dump()),headers=HEADERS)
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
    # Serialize cancellation with the runtime across its transaction commits.
    from sqlalchemy import text
    from app.infrastructure.database.session import engine
    await session.rollback()
    async with engine.connect() as lock:
        if not (await lock.execute(text('SELECT pg_try_advisory_lock(606029)'))).scalar():raise HTTPException(409,'التنفيذ جارٍ؛ اقرأ النتيجة قبل الإلغاء.')
        try:
            j=await session.get(Job,jid,populate_existing=True)
            if j.state not in {'DRAFT','APPROVED'}:raise HTTPException(409,'بدأ التنفيذ؛ لا يلغي الإلغاء المحلي منشوراً لدى Meta.')
            await service.claim(session,j,'CANCELLED')
            return JSONResponse(service.describe(j),headers=HEADERS)
        finally:await lock.execute(text('SELECT pg_advisory_unlock(606029)'));await lock.commit()

@router.post('/materials/{uid}/prepare-delivery')
async def prepare_delivery(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:return JSONResponse(await service.prepare_delivery(session,uid),headers=HEADERS)
    except ValueError as e:raise HTTPException(409,str(e)) from None

@router.get('/{jid}/provider-status')
async def provider_status(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    """Owner-only known-session status evidence, no uploads or finish calls."""
    owner(request);j=await session.get(Job,jid)
    if not j or not j.remote_session:raise HTTPException(404,'لا توجد جلسة Meta معروفة.')
    import httpx
    from app.adapters.publishing.facebook import FacebookProviderError
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
        try:
            provider=await service.provider(session,j,client)
            result=await provider._request('GET',j.remote_session['video_id'],params={'fields':'status'})
            details=await provider._request('GET',j.remote_session['video_id'],params={'fields':'id,description,from,permalink_url'})
            return JSONResponse({'video_id':j.remote_session['video_id'],'status':result.get('status'),'details':details,'read_only':True},headers=HEADERS)
        except FacebookProviderError as e:
            return JSONResponse({'video_id':j.remote_session['video_id'],'error_code':e.code,'read_only':True},headers=HEADERS,status_code=409)


@router.post('/{jid}/retire-unpublished')
async def retire_unpublished(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    j=(await session.execute(select(Job).where(Job.id==jid).with_for_update())).scalar_one_or_none()
    if not j:raise HTTPException(404,'Unknown job')
    # Same advisory lock as worker, prevents an in-flight reconciliation race.
    from sqlalchemy import text
    from app.infrastructure.database.session import engine
    async with engine.connect() as lock:
        if not (await lock.execute(text('SELECT pg_try_advisory_lock(606029)'))).scalar():raise HTTPException(409,'Worker active, read result first')
        try:
            try:return JSONResponse(await service.retire_unfinished(session,j),headers=HEADERS)
            except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:await lock.execute(text('SELECT pg_advisory_unlock(606029)'));await lock.commit()
