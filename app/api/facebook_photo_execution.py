"""Exact Page photo decisions. No content generation or implicit approval."""
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter,Request,Depends,HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,text
from app.infrastructure.database.session import get_session,engine
from app.infrastructure.database.models import FacebookExecutionModel as Job
from app.api.instagram_connections import owner,mutation_owner,HEADERS
from app.application import facebook_text_runtime as service
from app.application.instagram_oauth import digest
router=APIRouter(prefix='/api/connections/facebook/photo-posts',tags=['facebook-exact-photo'])
class PreviewTime(BaseModel):
    model_config=ConfigDict(extra='forbid')
    due_at:datetime|None=None
    timezone_name:str|None=Field(default=None,max_length=100)
class Approval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    snapshot_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    exact_words_approved:StrictBool
    public_page_approved:StrictBool
    rights_confirmed:StrictBool
    exact_image_approved:StrictBool
    private_bytes_disclosure_approved:StrictBool

@router.post('/materials/{uid}/preview')
async def preview(uid:UUID,request:Request,payload:PreviewTime=PreviewTime(),session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:return JSONResponse(await service.stage(session,uid,kind='IMAGE',**payload.model_dump()),headers=HEADERS)
    except ValueError as e:raise HTTPException(409,str(e)) from None

@router.get('/{jid}')
async def result(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    owner(request);j=await session.get(Job,jid)
    if not j or not j.runtime_snapshot or j.kind!='IMAGE':raise HTTPException(404,'محاولة صورة غير موجودة.')
    return JSONResponse(service.describe(j),headers=HEADERS)

@router.post('/{jid}/approve')
async def approve(jid:UUID,payload:Approval,request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request)
    if any(x is not True for x in [payload.exact_words_approved,payload.public_page_approved,payload.rights_confirmed,payload.exact_image_approved,payload.private_bytes_disclosure_approved]):raise HTTPException(409,'يلزم اعتماد النص والصورة والصفحة العامة والحقوق وإرسال البايتات صراحةً.')
    j=(await session.execute(select(Job).where(Job.id==jid).with_for_update())).scalar_one_or_none()
    if not j or not j.runtime_snapshot or j.kind!='IMAGE':raise HTTPException(404,'محاولة صورة غير موجودة.')
    try:return JSONResponse(await service.approve(session,j,payload.snapshot_hash,'owner-session:'+digest(token)),headers=HEADERS)
    except ValueError as e:raise HTTPException(409,str(e)) from None

@router.post('/{jid}/cancel')
async def cancel(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    async with engine.connect() as lock:
        if not (await lock.execute(text(f'SELECT pg_try_advisory_lock({service.LOCK})'))).scalar():raise HTTPException(409,'التنفيذ جارٍ، اقرأ النتيجة أولاً.')
        try:
            j=(await session.execute(select(Job).where(Job.id==jid).with_for_update())).scalar_one_or_none()
            if not j or j.kind!='IMAGE':raise HTTPException(404,'محاولة غير موجودة.')
            try:return JSONResponse(await service.cancel(session,j),headers=HEADERS)
            except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:await lock.execute(text(f'SELECT pg_advisory_unlock({service.LOCK})'));await lock.commit()

@router.post('/{jid}/verify-result')
async def verify_result(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    async with engine.connect() as lock:
        if not (await lock.execute(text(f'SELECT pg_try_advisory_lock({service.LOCK})'))).scalar():raise HTTPException(409,'التنفيذ جارٍ.')
        try:
            j=await session.get(Job,jid)
            if not j or not j.runtime_snapshot or j.kind!='IMAGE' or not j.post_id or j.state=='SENDING':raise HTTPException(409,'لا يوجد معرف نشر مؤكد للقراءة، لا إعادة إرسال.')
            try:
                await service.process_one(session,j)
                return JSONResponse(service.describe(j),headers=HEADERS)
            except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:await lock.execute(text(f'SELECT pg_advisory_unlock({service.LOCK})'));await lock.commit()

@router.get('/{jid}/inspection')
async def inspect_result(jid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    """Owner-only provider GET diagnostic. Never sends or changes a decision."""
    owner(request)
    j=await session.get(Job,jid)
    if not j or not j.runtime_snapshot or j.kind!='IMAGE' or not j.post_id or j.state=='SENDING':
        raise HTTPException(409,'Known photo result required; no resend.')
    import httpx
    from dataclasses import asdict
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
        try:
            p=await service.provider(session,j,client)
            r=await p.verify_post(j.post_id,expected_message=j.message)
            return JSONResponse(dict(**asdict(r),expected_message=j.message),headers=HEADERS)
        except Exception:
            raise HTTPException(409,'Provider inspection unavailable; no resend.') from None
