"""Connection-only TikTok OAuth. No uploads, execution or automatic refresh."""
import json,os,secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode,urlsplit
import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select,delete,text
from app.infrastructure.database.models import TikTokConnectionModel as Connection,TikTokOAuthFlowModel as Flow,PlatformAppSettingsModel
from app.application.managed_connections import key
from app.application.instagram_oauth import digest
from app.adapters.publishing import tiktok_login as login
BASE='/api/connections/tiktok'
COOKIE='nashr_tiktok_oauth'
SOURCE='https://developers.tiktok.com/docs/en/login-kit-web'
def now():return datetime.now(timezone.utc)
async def lock(s):await s.execute(text('SELECT pg_advisory_xact_lock(606030)'))
async def configuration(s,required=False):
    row=await s.get(PlatformAppSettingsModel,'tiktok_login');c={}
    if row:
        try:
            c=json.loads(key().decrypt(row.ciphertext.encode()))
            if not isinstance(c,dict):raise ValueError()
        except (InvalidToken,ValueError):raise ValueError('تعذر فتح إعداد TikTok.') from None
    missing=[k for k in ['client_key','client_secret','redirect_uri'] if not isinstance(c.get(k),str) or not c[k]]
    u=urlsplit(c.get('redirect_uri',''))
    if u.scheme!='https' or not u.hostname or u.path!=BASE+'/callback' or u.query or u.fragment or u.username or u.password:missing.append('redirect_uri')
    if c.get('config_reviewed') is not True:missing.append('config_reviewed')
    if not os.getenv('NASHR_AUTH_PASSWORD'):missing.append('owner_auth')
    try:key()
    except ValueError:missing.append('encryption_key')
    c['missing']=missing;c['fingerprint']=digest(json.dumps(c,sort_keys=True))
    if required and missing:raise ValueError('إعداد TikTok غير مكتمل. يلزم تطبيق وLogin Kit وصلاحية الهوية فقط.')
    return c

def payload(r,c):
    if not r:return None
    invalid=r.config_hash!=c['fingerprint'] or r.token_expires_at<=now() or r.last_check_ok is False
    return dict(open_id=r.open_id,display_name=r.display_name,scopes=r.scopes,enabled=r.enabled,state='DISABLED' if not r.enabled else 'RECONNECT_REQUIRED' if invalid else 'CONNECTED_AT_LAST_CHECK',connected_at=r.connected_at.isoformat(),expires_at=r.token_expires_at.isoformat(),last_check_at=r.last_check_at.isoformat() if r.last_check_at else None,last_check_ok=r.last_check_ok,execution_authorized=False,caveat='اسم عرض ومعرف خاص بالتطبيق، لا نثبت اسم المستخدم @ من صلاحية basic. لا رفع أو نشر. التحقق من آخر قراءة فقط. التجديد التلقائي غير مفعّل.')
async def status(s,owner,browser):
    c=await configuration(s);r=await s.get(Connection,1) if owner else None;pending=None
    if owner and browser:
        f=(await s.execute(select(Flow).where(Flow.session_hash==digest(owner),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)))).scalars().first()
        if f:pending={'accounts':f.accounts,'expires_at':f.expires_at.isoformat()}
    return dict(configured=not c['missing'],connection=payload(r,c),pending=pending,missing_configuration=c['missing'],execution_authorized=False,source=SOURCE)
async def begin(s,owner):
    c=await configuration(s,True);state=secrets.token_urlsafe(32);browser=secrets.token_urlsafe(32)
    await lock(s);await s.execute(delete(Flow).where((Flow.session_hash==digest(owner))|(Flow.expires_at<=now())))
    s.add(Flow(id=digest(state),session_hash=digest(owner),browser_hash=digest(browser),config_hash=c['fingerprint'],expires_at=now()+timedelta(minutes=10),consumed=False,accounts=[]));await s.commit()
    return 'https://www.tiktok.com/v2/auth/authorize/?'+urlencode(dict(client_key=c['client_key'],response_type='code',scope='user.info.basic',redirect_uri=c['redirect_uri'],state=state,disable_auto_auth='1')),browser
async def exchange(code,c):
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        tokens=await login.exchange(client,c,code);who=await login.identity(client,tokens['access_token'],tokens['open_id'])
        return tokens,who
async def finish(s,owner,browser,state,code,error=False):
    c=await configuration(s,True)
    if not browser or not state or len(state)>256:raise ValueError('جلسة غير صالحة.')
    await lock(s)
    f=(await s.execute(select(Flow).where(Flow.id==digest(state),Flow.session_hash==digest(owner),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.consumed.is_(False)).with_for_update())).scalar_one_or_none()
    if not f:raise ValueError('جلسة منتهية أو مستخدمة.')
    f.consumed=True;await s.commit()
    if error or not code or len(code)>8000:raise ValueError('أُلغي الإذن.')
    tokens,who=await exchange(code,c);tokens={**tokens,'access_expires_at':(now()+timedelta(seconds=tokens['expires_in'])).isoformat(),'refresh_expires_at':(now()+timedelta(seconds=tokens['refresh_expires_in'])).isoformat()}
    await lock(s);f=await s.get(Flow,digest(state),populate_existing=True)
    if not f or f.expires_at<=now() or (await configuration(s,True))['fingerprint']!=f.config_hash:raise ValueError('تغير الإعداد أثناء الربط.')
    f.token_ciphertext=key().encrypt(json.dumps(tokens).encode()).decode();f.accounts=[who];await s.commit()
async def selected_facts(tokens):
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:return await login.identity(client,tokens['access_token'],tokens['open_id'])
async def select_account(s,owner,browser,open_id):
    if not browser:raise ValueError('أعد الربط.')
    await lock(s);c=await configuration(s,True)
    f=(await s.execute(select(Flow).where(Flow.session_hash==digest(owner),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)).with_for_update())).scalars().first()
    if not f or not any(x.get('open_id')==open_id for x in f.accounts):raise ValueError('اختر الهوية من TikTok فقط.')
    try:
        t=json.loads(key().decrypt(f.token_ciphertext.encode()))
        if t['open_id']!=open_id or datetime.fromisoformat(t['access_expires_at'])<=now():raise ValueError()
        who=await selected_facts(t)
    except (InvalidToken,ValueError,TypeError,KeyError):raise ValueError('تعذر التحقق من الهوية. لم يتغير الربط السابق.') from None
    r=await s.get(Connection,1)
    if not r:r=Connection(id=1);s.add(r)
    r.open_id=who['open_id'];r.display_name=who['display_name'];r.token_ciphertext=f.token_ciphertext;r.config_hash=c['fingerprint'];r.scopes=['user.info.basic'];r.token_expires_at=datetime.fromisoformat(t['access_expires_at']);r.connected_at=now();r.last_check_at=now();r.last_check_ok=True;r.enabled=True
    await s.execute(delete(Flow).where(Flow.session_hash==digest(owner)));await s.commit()
async def verify(s):
    await lock(s);c=await configuration(s,True);r=await s.get(Connection,1,populate_existing=True)
    if not r or r.config_hash!=c['fingerprint'] or r.token_expires_at<=now():raise ValueError('أعد الربط، الرمز منتهٍ أو تغير إعداد التطبيق. لا تجديد تلقائي.')
    try:
        t=json.loads(key().decrypt(r.token_ciphertext.encode()))
        if t['open_id']!=r.open_id:raise ValueError()
        who=await selected_facts(t)
    except (InvalidToken,ValueError,TypeError,KeyError):
        r.last_check_at=now();r.last_check_ok=False;await s.commit();raise ValueError('فشل تحقق TikTok، لا تبديل حساب أو نشر.') from None
    r.display_name=who['display_name'];r.last_check_at=now();r.last_check_ok=True;await s.commit();return payload(r,c)
async def disconnect(s,owner):
    await lock(s);await s.execute(delete(Connection));await s.execute(delete(Flow));await s.commit()
