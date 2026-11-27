from uuid import UUID
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import JSONResponse,HTMLResponse
from pydantic import BaseModel,ConfigDict,Field,SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.instagram_connections import owner,mutation_owner,HEADERS
from app.infrastructure.database.session import get_session
from app.application import managed_connections as service
from app.api.frontend import frontend_index_response
router=APIRouter()

@router.get('/connections',include_in_schema=False)
async def page():return frontend_index_response() or HTMLResponse('<h1>Accounts dashboard bundle unavailable</h1>')

@router.get('/api/connections')
async def overview(request:Request,session:AsyncSession=Depends(get_session)):
    owner(request);return JSONResponse(await service.overview(session),headers=HEADERS)

class TelegramInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label:str=Field(min_length=1,max_length=100)
    token:SecretStr=Field(min_length=20,max_length=250)
    destination:str=Field(min_length=1,max_length=100)

@router.post('/api/connections/telegram')
async def add(payload:TelegramInput,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:uid=await service.add_telegram(session,payload.label,payload.token.get_secret_value(),payload.destination)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse({'id':uid,'active':False,'sent_messages':0},headers=HEADERS)

@router.post('/api/connections/telegram/{uid}/remove')
async def remove(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:await service.remove(session,uid)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse({'removed_locally':False,'disabled_locally':True,'history_preserved':True,'remote_revoked':False},headers=HEADERS)

class ChannelBatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    artifact_ids:list[UUID]=Field(min_length=1,max_length=100)
    connection_ids:list[UUID]=Field(min_length=1,max_length=20)

@router.post('/api/connections/telegram/preview')
async def channel_preview(payload:ChannelBatch,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    from app.application.telegram_batch_preview import preview_telegram_batch
    if len(set(payload.connection_ids))!=len(payload.connection_ids):raise HTTPException(422,'قنوات مكررة.')
    try:items=[await preview_telegram_batch(session,payload.artifact_ids,uid) for uid in payload.connection_ids]
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse({'channels':items,'sent_messages':0},headers=HEADERS)

from datetime import datetime
class ChannelPlans(ChannelBatch):
    name:str=Field(min_length=1,max_length=200)
    timezone:str
    start_at:datetime
    interval_minutes:int=Field(ge=1,le=10080)
    previews:list[dict]=Field(min_length=1,max_length=20)

@router.post('/api/connections/telegram/plans')
async def channel_plans(payload:ChannelPlans,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    from app.application.telegram_batch_schedule import create_telegram_batch_schedule
    from sqlalchemy import text
    if len(set(payload.connection_ids))!=len(payload.connection_ids):raise HTTPException(422,'قنوات مكررة.')
    await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
    plans=[]
    try:
        for uid in payload.connection_ids:
            preview=next((p for p in payload.previews if p.get('connection_id')==str(uid)),None)
            if not preview:raise ValueError('معاينة إحدى القنوات ناقصة.')
            row,_=await service.selected(session,uid)
            plans.append(await create_telegram_batch_schedule(session,artifact_ids=payload.artifact_ids,fingerprints={p['artifact_id']:p.get('source_fingerprint') for p in preview.get('items',[])},copy_versions={p['artifact_id']:p.get('copy_version') for p in preview.get('items',[])},name=payload.name+' · '+row.label,timezone_name=payload.timezone,start_at=payload.start_at,interval_minutes=payload.interval_minutes,destination=preview['destination'],connection_id=uid,commit=False))
        await session.commit()
    except (ValueError,KeyError,TypeError) as exc:
        await session.rollback();raise HTTPException(409,str(exc) if isinstance(exc,ValueError) else 'المعاينة غير مكتملة. حدّثها أولاً.') from None
    return JSONResponse({'plans':plans,'activated':False,'sent_messages':0},headers=HEADERS)

@router.get('/api/connections/telegram/{uid}/history')
async def history(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    owner(request)
    from sqlalchemy import select
    from app.infrastructure.database.models import PublicationModel,ScheduleModel
    from app.infrastructure.database.models import ManagedConnectionModel
    row=await session.get(ManagedConnectionModel,uid)
    if row is None or row.platform!='telegram':raise HTTPException(404,'الربط غير موجود.')
    pubs=(await session.execute(select(PublicationModel).where(PublicationModel.platform=='telegram',PublicationModel.connection_id==uid).order_by(PublicationModel.created_at.desc()).limit(100))).scalars().all()
    plans=(await session.execute(select(ScheduleModel).where(ScheduleModel.telegram_review['connection_id'].astext==str(uid)).order_by(ScheduleModel.created_at.desc()).limit(100))).scalars().all()
    return JSONResponse({'publications':[{'id':str(p.id),'artifact_id':str(p.artifact_id) if p.artifact_id else None,'status':p.status,'published_at':p.published_at.isoformat() if p.published_at else None,'destination':p.destination} for p in pubs],'plans':[{'id':str(p.id),'name':p.name,'status':p.status}for p in plans]},headers=HEADERS)

class MetaSettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    app_id:str=Field(pattern=r'^[0-9]{3,40}$')
    app_secret:SecretStr=Field(min_length=10,max_length=1000)
    config_id:str=Field(pattern=r'^[0-9]{3,40}$')
    redirect_uri:str=Field(max_length=500)
    config_reviewed:bool

@router.post('/api/connections/apps/instagram')
async def meta_settings(payload:MetaSettings,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    import json
    from app.infrastructure.database.models import PlatformAppSettingsModel,InstagramOAuthFlowModel
    from app.application.instagram_oauth import configuration
    from sqlalchemy import delete,text
    values={'META_APP_ID':payload.app_id,'META_APP_SECRET':payload.app_secret.get_secret_value(),'META_INSTAGRAM_CONFIG_ID':payload.config_id,'META_INSTAGRAM_REDIRECT_URI':payload.redirect_uri,'META_INSTAGRAM_CONFIG_REVIEWED':'true' if payload.config_reviewed else 'false'}
    try:
        crypt=service.key()
        c=configuration(values)
        if c['missing']:raise ValueError('إعداد التطبيق غير مكتمل أو عنوان العودة غير صالح أو الصلاحيات لم تُراجع.')
        from urllib.parse import urlsplit
        if urlsplit(payload.redirect_uri).netloc!=urlsplit(str(request.base_url)).netloc:raise ValueError('عنوان العودة يجب أن يطابق موقع Nashr الحالي.')
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    row=await session.get(PlatformAppSettingsModel,'instagram')
    if not row:row=PlatformAppSettingsModel(platform='instagram');session.add(row)
    row.ciphertext=crypt.encrypt(json.dumps(values).encode()).decode()
    await session.execute(delete(InstagramOAuthFlowModel));await session.commit()
    return JSONResponse({'saved':True,'secret_saved':True,'external_app_created':False,'account_connected':False},headers=HEADERS)


@router.post('/api/connections/telegram/import-legacy')
async def import_legacy(request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:result=await service.import_legacy(session)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

class TokenUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:SecretStr=Field(min_length=20,max_length=250)

@router.post('/api/connections/telegram/{uid}/token')
async def token_update(uid:UUID,payload:TokenUpdate,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:result=await service.rotate_token(session,uid,payload.token.get_secret_value())
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

@router.post('/api/connections/telegram/{uid}/verify')
async def verify(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:result=await service.verify_saved(session,uid)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

class EnabledInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled:bool

@router.post('/api/connections/telegram/{uid}/state')
async def state_update(uid:UUID,payload:EnabledInput,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:result=await service.set_enabled(session,uid,payload.enabled)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

@router.get('/api/connections/tiktok/requirements')
async def tiktok_requirements(request:Request):
    owner(request)
    from app.application.tiktok_policy import requirements
    return JSONResponse(requirements(),headers=HEADERS)


@router.get('/api/analytics/capabilities')
async def analytics_capabilities(request: Request, session: AsyncSession = Depends(get_session)):
    owner(request)
    from app.application.analytics_capabilities import capabilities
    return JSONResponse(await capabilities(session), headers=HEADERS)
