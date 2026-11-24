"""Explicit Page-linked login. Separate storage from existing Unified connections.

No fall back between modes, Page creation/linking, publication or token refresh.
"""
import json,os,re,secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode,urlsplit
import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select,delete,text
from app.infrastructure.database.models import FacebookPageOAuthFlowModel as Flow,FacebookPageConnectionModel as Connection,PlatformAppSettingsModel
from app.application.managed_connections import key
from app.application.instagram_oauth import digest
from app.adapters.publishing.facebook_page_login import FacebookPagesLogin,FacebookPageCandidate,FacebookLoginError

BASE='/api/connections/facebook'
COOKIE='nashr_facebook_page_oauth'
SOURCE='https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business'

class OAuthFailure(ValueError):
    """Fixed, secret-free reason safe for callback UI and logs."""
    def __init__(self,reason):
        allowed={'SESSION','CANCELLED','TOKEN_EXCHANGE','NO_ELIGIBLE_ACCOUNT','PERMISSIONS','TOKEN_IDENTITY','DISCOVERY','CONFIG_CHANGED'}
        self.reason=reason if reason in allowed else 'DISCOVERY'
        super().__init__(self.reason)

def now():return datetime.now(timezone.utc)

async def configuration(session,required=False):
    row=await session.get(PlatformAppSettingsModel,'facebook_page')
    c={}
    if row:
        try:
            c=json.loads(key().decrypt(row.ciphertext.encode()))
            if not isinstance(c,dict):raise ValueError()
        except (ValueError,InvalidToken):raise ValueError('تعذر فتح إعداد مسار الصفحة. لن نستخدم إعداد Instagram بديلاً.') from None
    missing=[]
    for name in ['app_id','app_secret','config_id','redirect_uri']:
        if not isinstance(c.get(name),str) or not c[name]:missing.append(name)
    if c.get('config_reviewed') is not True:missing.append('config_reviewed')
    if c.get('token_mode') not in {'USER','SYSTEM_USER'}:missing.append('token_mode')
    for name in ['app_id','config_id']:
        if c.get(name) and not re.fullmatch('[0-9]{3,40}',c[name]):missing.append(name)
    u=urlsplit(c.get('redirect_uri',''))
    if c.get('redirect_uri') and (u.scheme!='https' or not u.hostname or u.path!=BASE+'/callback' or u.query or u.fragment or u.username or u.password):missing.append('redirect_uri')
    if not os.getenv('NASHR_AUTH_PASSWORD'):missing.append('owner_auth')
    try:key()
    except ValueError:missing.append('encryption_key')
    c['missing']=missing;c['fingerprint']=digest(json.dumps(c,sort_keys=True))
    if required and missing:raise ValueError('إعداد Facebook غير مكتمل. لا نستخدم Instagram بديلاً.')
    return c

async def lock(session):await session.execute(text('SELECT pg_advisory_xact_lock(606028)'))

def payload(row,c):
    if not row:return None
    invalid=row.config_hash!=c['fingerprint'] or row.token_expires_at is not None and row.token_expires_at<=now() or row.last_check_ok is False
    return dict(page_id=row.page_id,page_name=row.page_name,token_type=row.token_type,tasks=row.tasks,scopes=row.scopes,enabled=row.enabled,state='DISABLED' if not row.enabled else 'RECONNECT_REQUIRED' if invalid else 'CONNECTED_AT_LAST_CHECK',connected_at=row.connected_at.isoformat(),expires_at=row.token_expires_at.isoformat() if row.token_expires_at else None,last_check_at=row.last_check_at.isoformat() if row.last_check_at else None,last_check_ok=row.last_check_ok,execution_authorized=False,caveat='هوية وصلاحية من آخر تحقق فقط. الربط لا ينشر ولا يغير Instagram أو يتيح الوسائط.')

async def status(session,session_token,browser):
    c=await configuration(session);row=await session.get(Connection,1) if session_token else None;pending=None
    if session_token and browser:
        flow=(await session.execute(select(Flow).where(Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)))).scalars().first()
        if flow:pending={'accounts':flow.accounts,'expires_at':flow.expires_at.isoformat()}
    return dict(configured=not c['missing'],missing_configuration=c['missing'],connection=payload(row,c),pending=pending,execution_authorized=False,flow='FACEBOOK_PAGES',source=SOURCE,requirements=['صفحة Facebook بصلاحية CREATE_CONTENT موثقة من Meta.','إعداد مستقل على التطبيق نفسه، لا تغيير إعداد Instagram.','pages_show_list وpages_read_engagement وpages_manage_posts فقط، لا إعلانات أو رسائل.','اختيار الصفحة صراحةً بعد الرجوع من Meta. لا نشر أو اختبار تلقائي.'])

async def begin(session,session_token):
    c=await configuration(session,True);state=secrets.token_urlsafe(32);browser=secrets.token_urlsafe(32)
    await lock(session);await session.execute(delete(Flow).where(Flow.expires_at<=now()));await session.execute(delete(Flow).where(Flow.session_hash==digest(session_token)))
    session.add(Flow(id=digest(state),session_hash=digest(session_token),browser_hash=digest(browser),config_hash=c['fingerprint'],expires_at=now()+timedelta(minutes=10),consumed=False,accounts=[]))
    await session.commit()
    return 'https://www.facebook.com/dialog/oauth?'+urlencode(dict(client_id=c['app_id'],config_id=c['config_id'],redirect_uri=c['redirect_uri'],response_type='code',state=state)),browser

async def exchange(code,c):
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        try:
            r=await client.get('https://graph.facebook.com/v27.0/oauth/access_token',params=dict(client_id=c['app_id'],client_secret=c['app_secret'],redirect_uri=c['redirect_uri'],code=code),follow_redirects=False)
            d=r.json();token=d.get('access_token') if isinstance(d,dict) else None
            if r.status_code!=200 or not isinstance(token,str) or not token or len(token)>16000:raise ValueError()
        except (ValueError,TypeError,httpx.HTTPError):raise OAuthFailure('TOKEN_EXCHANGE') from None
        return await FacebookPagesLogin(client=client,app_id=c['app_id'],app_secret=c['app_secret'],token_mode=c['token_mode']).discover(token)

async def finish(session,session_token,browser,state,code,error=False):
    c=await configuration(session,True)
    if not browser or not state or len(state)>256:raise OAuthFailure('SESSION')
    await lock(session)
    flow=(await session.execute(select(Flow).where(Flow.id==digest(state),Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.consumed.is_(False)).with_for_update())).scalar_one_or_none()
    if not flow:raise OAuthFailure('SESSION')
    flow.consumed=True;await session.commit()
    if error or not code or len(code)>8000:raise OAuthFailure('CANCELLED')
    try:candidates=await exchange(code,c)
    except FacebookLoginError as exc:
        reason={'FACEBOOK_PAGES_NO_ELIGIBLE_PAGE':'NO_ELIGIBLE_ACCOUNT','FACEBOOK_PAGES_PERMISSION_REQUIRED':'PERMISSIONS','FACEBOOK_PAGES_TOKEN_MISMATCH':'TOKEN_IDENTITY'}.get(str(exc),'DISCOVERY')
        raise OAuthFailure(reason) from None
    await lock(session)
    flow=await session.get(Flow,digest(state),populate_existing=True)
    if not flow or flow.expires_at<=now() or flow.config_hash!=(await configuration(session,True))['fingerprint']:raise OAuthFailure('CONFIG_CHANGED')
    from dataclasses import asdict
    flow.accounts=[x.public() for x in candidates]
    flow.token_ciphertext=key().encrypt(json.dumps([asdict(x) for x in candidates]).encode()).decode()
    await session.commit()

async def selected_facts(c,candidate):
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        return await FacebookPagesLogin(client=client,app_id=c['app_id'],app_secret=c['app_secret'],token_mode=c['token_mode']).verify_selected(candidate)

async def select_account(session,session_token,browser,page_id):
    if not browser:raise ValueError('جلسة اختيار منتهية.')
    await lock(session)
    c=await configuration(session,True)
    flow=(await session.execute(select(Flow).where(Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)).with_for_update())).scalars().first()
    if not flow:raise ValueError('أعد الربط من Nashr.')
    try:
        entries=json.loads(key().decrypt(flow.token_ciphertext.encode()));chosen=next((x for x in entries if x['page_id']==page_id),None)
        if not chosen:raise ValueError('اختر حساباً من قائمة Meta المعروضة فقط.')
        candidate=FacebookPageCandidate(**chosen)
        facts=await selected_facts(c,candidate)
    except (InvalidToken,FacebookLoginError,ValueError,TypeError,KeyError):raise ValueError('تغيرت هوية الصفحة أو صلاحية الحساب. أعد الربط دون استبدال السابق.') from None
    row=await session.get(Connection,1)
    if not row:row=Connection(id=1);session.add(row)
    row.page_id=candidate.page_id;row.page_name=candidate.page_name;row.tasks=list(facts['tasks']);row.scopes=list(facts['scopes']);row.token_type=candidate.token_type
    row.token_ciphertext=key().encrypt(json.dumps({'page_token':candidate.token,'source_token':candidate.source_token}).encode()).decode();row.config_hash=c['fingerprint'];row.token_expires_at=datetime.fromtimestamp(facts['expires_at'],timezone.utc) if facts['expires_at'] else None
    row.connected_at=now();row.last_check_at=now();row.last_check_ok=True;row.enabled=True
    await session.execute(delete(Flow).where(Flow.session_hash==digest(session_token)));await session.commit()

async def verify_saved_connection(session,**_):
    await lock(session);c=await configuration(session,True);row=await session.get(Connection,1,populate_existing=True)
    if not row or row.config_hash!=c['fingerprint'] or row.token_expires_at and row.token_expires_at<=now():raise ValueError('الربط غير موجود أو تغير إعداده أو انتهت صلاحيته. أعد الربط.')
    try:
        tokens=json.loads(key().decrypt(row.token_ciphertext.encode()));candidate=FacebookPageCandidate(page_id=row.page_id,page_name=row.page_name,tasks=tuple(row.tasks),scopes=tuple(row.scopes),token_type=row.token_type,token=tokens['page_token'],expires_at=int(row.token_expires_at.timestamp()) if row.token_expires_at else None,source_token=tokens['source_token'])
        facts=await selected_facts(c,candidate)
    except (FacebookLoginError,InvalidToken,ValueError,TypeError,KeyError):
        row.last_check_at=now();row.last_check_ok=False;await session.commit();raise ValueError('لم ينجح تحقق الصفحة والحساب. لا نشر أو تبديل حساب.') from None
    row.last_check_at=now();row.last_check_ok=True;row.tasks=list(facts['tasks']);row.scopes=list(facts['scopes'])
    if facts['expires_at']:row.token_expires_at=datetime.fromtimestamp(facts['expires_at'],timezone.utc)
    await session.commit();return payload(row,c)

async def set_connection_enabled(session,enabled):
    await lock(session);c=await configuration(session);row=await session.get(Connection,1,populate_existing=True)
    if not row:raise ValueError('لا يوجد ربط صفحة محفوظ.')
    if enabled and (row.config_hash!=c['fingerprint'] or row.last_check_ok is not True or row.last_check_at is None or row.last_check_at<now()-timedelta(minutes=5) or row.token_expires_at and row.token_expires_at<=now()):raise ValueError('تحقق من الحساب الآن قبل التفعيل المحلي.')
    row.enabled=enabled;await session.commit()

async def disconnect(session,session_token):
    await lock(session);await session.execute(delete(Connection));await session.execute(delete(Flow));await session.commit()
