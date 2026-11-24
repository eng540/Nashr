"""Connection lifecycle only, never publishing or personal sign-in."""
import os
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
    allowed={(expected.scheme,expected.netloc)}
    # Railway terminates TLS before ASGI. Trust its configured public domain,
    # never arbitrary forwarded headers or the caller's Origin as configuration.
    domain=os.getenv('RAILWAY_PUBLIC_DOMAIN','').strip().lower()
    if domain and '/' not in domain and ':' not in domain and expected.hostname==domain:
        allowed.add(('https',domain))
    if not origin or (actual.scheme,actual.netloc) not in allowed or actual.path or actual.query or actual.fragment or actual.username or request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'الطلب يجب أن يبدأ من Nashr نفسه.')
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

from datetime import datetime
from uuid import UUID
from pydantic import StrictBool

class PlanReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    share_to_feed:StrictBool|None=None
    planned_at:datetime|None=None
    timezone_name:str|None=Field(default=None,max_length=100)

class SavePlanReview(PlanReview):
    preview_hash:str=Field(pattern=r'^[a-f0-9]{64}$')

@router.post('/materials/{uid}/preview')
async def plan_preview(uid:UUID,payload:PlanReview,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    from app.application.instagram_plan_review import preview
    try:result=await preview(session,uid,share_to_feed=payload.share_to_feed,planned_at=payload.planned_at,timezone_name=payload.timezone_name)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

@router.post('/materials/{uid}/drafts')
async def save_plan_review(uid:UUID,payload:SavePlanReview,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    from app.application.instagram_plan_review import save_draft
    try:result=await save_draft(session,uid,preview_hash=payload.preview_hash,share_to_feed=payload.share_to_feed,planned_at=payload.planned_at,timezone_name=payload.timezone_name)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)

@router.get('/materials/{uid}/drafts')
async def plan_review_history(uid:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    owner(request)
    from app.application.instagram_plan_review import list_drafts
    try:result=await list_drafts(session,uid)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)


@router.post('/materials/{uid}/drafts/{draft_id}/cancel')
async def cancel_plan_review(uid:UUID,draft_id:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    mutation_owner(request)
    from app.application.instagram_plan_review import cancel_review_draft
    try:result=await cancel_review_draft(session,uid,draft_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    return JSONResponse(result,headers=HEADERS)
