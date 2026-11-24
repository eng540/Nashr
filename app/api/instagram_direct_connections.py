"""Connection lifecycle only, never publishing or personal sign-in."""
import os
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse,HTMLResponse
from pydantic import BaseModel,ConfigDict,Field,SecretStr,StrictBool
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import SESSION_COOKIE,auth_enabled,verify_token
from app.infrastructure.database.session import get_session
from app.application import instagram_direct_oauth as service
router=APIRouter(prefix=service.BASE,tags=['instagram-direct-connection'])
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
    except ValueError as exc:
        # Only our allowlisted reason is rendered/logged. Never provider text,
        # query values, exception strings, tokens, account IDs or secrets.
        reason=exc.reason if isinstance(exc,service.DirectFailure) else 'CONFIGURATION'
        messages={
            'SESSION':'جلسة الربط غير صالحة أو مستخدمة أو انتهت. ابدأ من Nashr في المتصفح نفسه.',
            'CANCELLED':'لم يكتمل إذن Instagram.',
            'TOKEN_EXCHANGE':'تعذر تبادل رمز Instagram. راجع إعداد Instagram Login وعنوان العودة.',
            'PERMISSIONS':'لم يمنح Instagram صلاحيتي الحساب والنشر المطلوبتين.',
            'IDENTITY':'لم يتطابق حساب Instagram مع نتيجة الدخول. لم يتغير الربط السابق.',
            'EXPIRY':'لم يرجع Instagram مدة صلاحية موثقة للرمز.',
            'PROVIDER':'تعذر إكمال تحقق Instagram. لا إعادة محاولة صامتة.',
            'CONFIG_CHANGED':'انتهت المحاولة أو تغير إعداد Instagram Login.',
            'CONFIGURATION':'إعداد Instagram Login غير مكتمل أو تغير.'}
        import logging
        logging.getLogger(__name__).warning('Instagram Direct OAuth callback failed: %s',reason)
        text=messages.get(reason,messages['PROVIDER'])
        return HTMLResponse('<html lang="ar" dir="rtl"><meta name="referrer" content="no-referrer"><meta name="viewport" content="width=device-width, initial-scale=1"><p>'+text+'</p><p>لم يتغير الربط السابق. لا نشر أو إذن تنفيذ.</p><p>مرجع التشخيص: '+reason+'</p><a href="/connections">العودة إلى Nashr</a></html>',status_code=400,headers=HEADERS)
    return RedirectResponse('/connections',status_code=303,headers=HEADERS)

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    account_id:str=Field(pattern=r'^[0-9]{1,100}$')

@router.post('/select')
async def select_account(payload:Selection,request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request)
    try:await service.select_account(session,token,request.cookies.get(service.COOKIE),payload.account_id)
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
    try:result=await service.verify_saved_connection(session)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse({'connection':result,'sent_messages':0,'execution_authorized':False},headers=HEADERS)

class LocalState(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    enabled:bool

@router.post('/state')
async def local_state(payload:LocalState,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    try:await service.set_connection_enabled(session,payload.enabled)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse({'enabled':payload.enabled,'remote_changed':False,'sent_messages':0,'execution_authorized':False},headers=HEADERS)

class DirectSettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    app_id:str=Field(pattern=r'^[0-9]{3,40}$')
    app_secret:SecretStr=Field(min_length=10,max_length=1000)
    redirect_uri:str=Field(max_length=500)
    direct_login_reviewed:StrictBool

@router.post('/settings')
async def settings(payload:DirectSettings,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    from app.infrastructure.database.models import PlatformAppSettingsModel,InstagramDirectOAuthFlowModel
    from app.application.managed_connections import key
    from sqlalchemy import delete
    import json
    from urllib.parse import urlsplit
    u=urlsplit(payload.redirect_uri);actual=urlsplit(str(request.base_url))
    if payload.direct_login_reviewed is not True or u.scheme!='https' or u.netloc!=actual.netloc or u.path!=service.BASE+'/callback' or u.query or u.fragment or u.username or u.password:
        raise HTTPException(409,'راجع إعداد Instagram Login المباشر وعنوان العودة على موقع Nashr نفسه.')
    await service.lock(session)
    values=payload.model_dump();values['app_secret']=payload.app_secret.get_secret_value()
    try:encrypted=key().encrypt(json.dumps(values).encode()).decode()
    except ValueError:raise HTTPException(409,'حماية الأسرار غير مهيأة. لم يحفظ الإعداد.') from None
    row=await session.get(PlatformAppSettingsModel,'instagram_direct')
    if not row:row=PlatformAppSettingsModel(platform='instagram_direct');session.add(row)
    row.ciphertext=encrypted
    await session.execute(delete(InstagramDirectOAuthFlowModel));await session.commit()
    return JSONResponse({'saved':True,'secret_saved':True,'account_connected':False,'other_connections_changed':False},headers=HEADERS)
