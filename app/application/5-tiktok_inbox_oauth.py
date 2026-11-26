"""Independent Sandbox draft consent. No uploads, execution or refresh."""
import json,os,secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select,delete,text
from app.infrastructure.database.models import TikTokInboxConnectionModel as Connection,TikTokInboxOAuthFlowModel as Flow
from app.application.managed_connections import key
from app.application.instagram_oauth import digest
from app.adapters.publishing import tiktok_inbox_login as login
BASE='/api/connections/tiktok-inbox'
COOKIE='nashr_tiktok_inbox_oauth'
SOURCE='https://developers.tiktok.com/docs/en/add-a-sandbox'
def now():return datetime.now(timezone.utc)
async def lock(s):await s.execute(text('SELECT pg_advisory_xact_lock(606032)'))
async def configuration(s,required=False):
    from app.application.tiktok_oauth import configuration as basic_configuration
    try:
        key()
        base=await basic_configuration(s)
    except (ValueError,TypeError):raise ValueError('حماية أسرار TikTok غير متاحة. لم يتغير الإذن المحفوظ.') from None
    c={k:v for k,v in base.items() if k not in {'fingerprint','missing'}}
    c['redirect_uri']=c.get('redirect_uri','').replace('/api/connections/tiktok/callback',BASE+'/callback')
    c['missing']=list(base['missing'])
    if os.getenv('NASHR_TIKTOK_INBOX_SANDBOX_REVIEWED')!='true':c['missing'].append('sandbox_upload_product_and_callback_review')
    c['mode']='SANDBOX_DRAFT_CONSENT_ONLY'
    c['fingerprint']=digest(json.dumps(c,sort_keys=True))
    if required and c['missing']:raise ValueError('يلزم إعداد Content Posting API للمسودات وعنوان العودة المستقل في Sandbox. لا نشر عام.')
    return c

def payload(r,c,basic=None):
    if not r:return None
    invalid=not basic or basic.open_id!=r.open_id or not basic.enabled or bool(c['missing']) or r.config_hash!=c['fingerprint'] or not r.token_expires_at or r.token_expires_at<=now() or r.last_check_ok is False
    return dict(open_id=r.open_id,display_name=r.display_name,scopes=r.scopes,enabled=r.enabled,state='DISABLED' if not r.enabled else 'RECONNECT_REQUIRED' if invalid else 'CONNECTED_AT_LAST_CHECK',connected_at=r.connected_at.isoformat(),expires_at=r.token_expires_at.isoformat() if r.token_expires_at else None,last_check_at=r.last_check_at.isoformat() if r.last_check_at else None,last_check_ok=r.last_check_ok,execution_authorized=False,caveat='إذن Sandbox للمسودات فقط، لا يثبت النشر العام أو نجاح النقل. لا توجد عملية نقل أو نشر أو تجديد آلي في هذا التدفق. إكمال المسودة لاحقًا داخل TikTok بعد إشعار الوارد.')
async def status(s,owner,browser):
    c=await configuration(s);r=await s.get(Connection,1) if owner else None;pending=None
    if owner and browser:
        f=(await s.execute(select(Flow).where(Flow.session_hash==digest(owner),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)))).scalars().first()
        if f:pending={'accounts':f.accounts,'expires_at':f.expires_at.isoformat()}
    from app.infrastructure.database.models import TikTokConnectionModel
    basic=await s.get(TikTokConnectionModel,1) if r else None
    return dict(configured=not c['missing'],connection=payload(r,c,basic),pending=pending,missing_configuration=c['missing'],execution_authorized=False,transfer_available=False,public_posting_available=False,mode='SANDBOX_DRAFT_CONSENT_ONLY',source=SOURCE)
async def begin(s,owner):
    c=await configuration(s,True);state=secrets.token_urlsafe(32);browser=secrets.token_urlsafe(32)
    await lock(s);await s.execute(delete(Flow).where((Flow.session_hash==digest(owner))|(Flow.expires_at<=now())))
    s.add(Flow(id=digest(state),session_hash=digest(owner),browser_hash=digest(browser),config_hash=c['fingerprint'],expires_at=now()+timedelta(minutes=10),consumed=False,accounts=[]));await s.commit()
    return 'https://www.tiktok.com/v2/auth/authorize/?'+urlencode(dict(client_key=c['client_key'],response_type='code',scope='user.info.basic,video.upload',redirect_uri=c['redirect_uri'],state=state,disable_auto_auth='1')),browser
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
    await s.execute(text('SELECT pg_advisory_xact_lock(606030)'))
    if (await configuration(s,True))['fingerprint']!=f.config_hash:raise ValueError('تغير الإعداد أثناء حفظ الإذن.')
    from app.infrastructure.database.models import TikTokConnectionModel
    basic=await s.get(TikTokConnectionModel,1)
    if not basic or basic.open_id!=open_id:raise ValueError('يجب أن تطابق الهوية اتصال TikTok الأساسي المحفوظ. لم يتغير أي اتصال.')
    r=await s.get(Connection,1)
    if not r:r=Connection(id=1);s.add(r)
    r.open_id=who['open_id'];r.display_name=who['display_name'];r.token_ciphertext=f.token_ciphertext;r.config_hash=c['fingerprint'];r.scopes=['user.info.basic','video.upload'];r.token_expires_at=datetime.fromisoformat(t['access_expires_at']);r.connected_at=now();r.last_check_at=now();r.last_check_ok=True;r.enabled=True
    await s.execute(delete(Flow).where(Flow.session_hash==digest(owner)));await s.commit()
async def verify(s):
    await lock(s);c=await configuration(s,True);r=await s.get(Connection,1,populate_existing=True)
    if not r or r.config_hash!=c['fingerprint'] or not r.token_expires_at or r.token_expires_at<=now():raise ValueError('أعد الربط، الرمز منتهٍ أو تغير إعداد التطبيق. لا تجديد تلقائي.')
    from app.infrastructure.database.models import TikTokConnectionModel
    basic=await s.get(TikTokConnectionModel,1)
    if not basic or not basic.enabled or basic.open_id!=r.open_id:raise ValueError('تغير اتصال الهوية الأساسي. راجع الإذن قبل التحقق.')
    try:
        t=json.loads(key().decrypt(r.token_ciphertext.encode()))
        if t['open_id']!=r.open_id:raise ValueError()
        who=await selected_facts(t)
    except (InvalidToken,ValueError,TypeError,KeyError):
        r.last_check_at=now();r.last_check_ok=False;await s.commit();raise ValueError('فشل تحقق TikTok، لا تبديل حساب أو نشر.') from None
    r.display_name=who['display_name'];r.last_check_at=now();r.last_check_ok=True;await s.commit();return payload(r,c,basic)
async def disconnect(s,owner):
    await lock(s);await s.execute(delete(Connection));await s.execute(delete(Flow));await s.commit()


async def cleanup_expired_flows():
    """Remove expired temporary candidates, never the selected connection.

    Use the lifecycle lock without waiting, so an active OAuth operation cannot
    hold up publishing. A later scheduler cycle retries a busy database.
    """
    from app.infrastructure.database.session import SessionFactory
    async with SessionFactory() as session:
        acquired = await session.scalar(text('SELECT pg_try_advisory_xact_lock(606032)'))
        if not acquired:
            return 0
        result = await session.execute(delete(Flow).where(Flow.expires_at <= now()))
        await session.commit()
        return result.rowcount
