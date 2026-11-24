"""Connection lifecycle only, never publishing or personal sign-in."""
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse,HTMLResponse
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import SESSION_COOKIE,auth_enabled,verify_token
from app.infrastructure.database.session import get_session
from app.application import instagram_oauth as service
router=APIRouter(prefix=service.BASE,tags=['instagram-connection'])
HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}

def owner(request):
    token=request.cookies.get(SESSION_COOKIE,'')
    if not auth_enabled() or not verify_token(token):raise HTTPException(401,'يلزم تسجيل دخول Nashr لتغيير الربط.')
    return token

def mutation_owner(request):
    token=owner(request);origin=request.headers.get('origin','')
    expected=urlsplit(str(request.base_url));actual=urlsplit(origin)
    if not origin or actual.scheme!=expected.scheme or actual.netloc!=expected.netloc or request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'الطلب يجب أن يبدأ من Nashr نفسه.')
    return token

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
        # Fixed error only, never reflect provider query text or the code.
        return HTMLResponse('<html lang="ar" dir="rtl"><meta name="referrer" content="no-referrer"><p>لم يكتمل الربط أو انتهت جلسته. لم يتغير الربط السابق.</p><a href="/connections">العودة إلى Nashr وبدء محاولة جديدة</a></html>',status_code=400,headers=HEADERS)
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
