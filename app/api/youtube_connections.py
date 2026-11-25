"""Connection lifecycle only, never publishing or personal sign-in."""
import os
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse,HTMLResponse
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,SecretStr,StrictBool
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import SESSION_COOKIE,auth_enabled,verify_token
from app.infrastructure.database.session import get_session
from app.application import youtube_oauth as service
router=APIRouter(prefix=service.BASE,tags=['youtube-identity-connection'])
HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}

from app.api.instagram_connections import owner,mutation_owner

@router.get('')
async def status(request:Request,session:AsyncSession=Depends(get_session)):
    token=request.cookies.get(SESSION_COOKIE,'')
    if not auth_enabled() or not verify_token(token):token=''
    return JSONResponse(await service.status(session,token,request.cookies.get(service.COOKIE)),headers=HEADERS)

@router.post('/start')
async def start(request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request)
    try:url,browser=await service.begin(session,token)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    response=JSONResponse({'authorization_url':url},headers=HEADERS)
    response.set_cookie(service.COOKIE,browser,max_age=600,secure=True,httponly=True,samesite='lax',path=service.BASE)
    return response

@router.get('/callback')
async def callback(request:Request,session:AsyncSession=Depends(get_session)):
    token=owner(request)
    query=getattr(request.state,'instagram_oauth_query',{})
    try:
        await service.finish(session,token,request.cookies.get(service.COOKIE),query.get('state',''),query.get('code',''),error=bool(query.get('error')))
    except ValueError:
        return HTMLResponse('<html lang="ar" dir="rtl"><meta name="referrer" content="no-referrer"><p>لم يكتمل ربط YouTube أو انتهت الجلسة. لم يتغير الربط السابق. راجع إعداد التطبيق وابدأ من Nashr مجدداً.</p><a href="/connections">العودة إلى Nashr</a></html>',status_code=400,headers=HEADERS)
    return RedirectResponse('/connections',status_code=303,headers=HEADERS)

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    channel_id:str=Field(min_length=1,pattern=r'^UC[A-Za-z0-9_-]{22}$')

@router.post('/select')
async def select_account(payload:Selection,request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request)
    try:await service.select_account(session,token,request.cookies.get(service.COOKIE),payload.channel_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    response=JSONResponse({'connected':True,'execution_authorized':False},headers=HEADERS);response.delete_cookie(service.COOKIE,path=service.BASE)
    return response

@router.post('/disconnect')
async def disconnect(request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request);await service.disconnect(session,token)
    response=JSONResponse({'disconnected_locally':True,'remote_revoked':False},headers=HEADERS);response.delete_cookie(service.COOKIE,path=service.BASE)
    return response

@router.post('/verify')
async def verify_connection(request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:return JSONResponse({'connection':await service.verify(session),'execution_authorized':False},headers=HEADERS)
    except ValueError as e:raise HTTPException(409,str(e)) from None

class Settings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_id:str=Field(min_length=5,max_length=200)
    client_secret:SecretStr=Field(min_length=10,max_length=1000)
    redirect_uri:str=Field(max_length=511)
    oauth_status:Literal["TESTING","PUBLISHED"]
    config_reviewed:StrictBool

@router.post('/settings')
async def settings(payload:Settings,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    u=urlsplit(payload.redirect_uri);actual=urlsplit(str(request.base_url))
    if not payload.config_reviewed or u.scheme!='https' or u.netloc!=actual.netloc or u.path!=service.BASE+'/callback' or u.query or u.fragment or u.username or u.password:raise HTTPException(409,'راجع عنوان العودة وإعداد Google Web OAuth للقراءة فقط.')
    from app.infrastructure.database.models import PlatformAppSettingsModel,YouTubeOAuthFlowModel
    from sqlalchemy import delete
    import json
    values=payload.model_dump();values['client_secret']=payload.client_secret.get_secret_value()
    await service.lock(session)
    try:encrypted=service.key().encrypt(json.dumps(values).encode()).decode()
    except ValueError:raise HTTPException(409,'حماية الأسرار غير مهيأة.') from None
    r=await session.get(PlatformAppSettingsModel,'youtube_readonly')
    if not r:r=PlatformAppSettingsModel(platform='youtube_readonly');session.add(r)
    r.ciphertext=encrypted;await session.execute(delete(YouTubeOAuthFlowModel));await session.commit()
    return JSONResponse({'saved':True,'connected':False,'execution_authorized':False},headers=HEADERS)
