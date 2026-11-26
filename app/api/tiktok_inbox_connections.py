"""Connection lifecycle only, never publishing or personal sign-in."""
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse,HTMLResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import SESSION_COOKIE,auth_enabled,verify_token
from app.infrastructure.database.session import get_session
from app.application import tiktok_inbox_oauth as service
router=APIRouter(prefix=service.BASE,tags=['tiktok-sandbox-draft-consent'])
HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}

from app.api.instagram_connections import owner,mutation_owner

@router.get('')
async def status(request:Request,session:AsyncSession=Depends(get_session)):
    token=request.cookies.get(SESSION_COOKIE,'')
    if not auth_enabled() or not verify_token(token):token=''
    return JSONResponse(await service.status(session,token,request.cookies.get(service.COOKIE)),headers=HEADERS)

class StartConsent(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reviewed:StrictBool

@router.post('/start')
async def start(payload:StartConsent,request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request)
    if payload.reviewed is not True:raise HTTPException(409,'راجع إذن المسودات وحدود Sandbox أولاً.')
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
        return HTMLResponse('<html lang="ar" dir="rtl"><meta name="referrer" content="no-referrer"><p>لم يكتمل إذن مسودات TikTok. تحقق من إعداد التطبيق وحماية الأسرار وصلاحية الجلسة في Nashr. لم يتغير الربط السابق، ولم يُنقل أو يُنشر فيديو.</p><a href="/connections">العودة إلى Nashr</a></html>',status_code=400,headers=HEADERS)
    return RedirectResponse('/connections#platform-tiktok-inbox',status_code=303,headers=HEADERS)

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    open_id:str=Field(min_length=1,max_length=100)

@router.post('/select')
async def select_account(payload:Selection,request:Request,session:AsyncSession=Depends(get_session)):
    token=mutation_owner(request)
    try:await service.select_account(session,token,request.cookies.get(service.COOKIE),payload.open_id)
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
