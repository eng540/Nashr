"""Owner-driven Unified Login. No publication endpoints or password collection."""
import hashlib
import json
import os
import re
import secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode,urlsplit
import httpx
from cryptography.fernet import Fernet,InvalidToken
from sqlalchemy import delete,select,update,text
from app.infrastructure.database.models import InstagramOAuthFlowModel as Flow,InstagramConnectionModel as Connection

COOKIE='nashr_instagram_oauth'
BASE='/api/connections/instagram'
REQUIRED={'instagram_basic','instagram_content_publish'}
SOURCE='https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started'

def now():return datetime.now(timezone.utc)
def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def configuration(overrides=None):
    names=['META_APP_ID','META_APP_SECRET','META_INSTAGRAM_CONFIG_ID','META_INSTAGRAM_REDIRECT_URI','NASHR_CONNECTION_ENCRYPTION_KEY']
    values={k:os.getenv(k,'').strip() for k in names}
    if overrides:values.update(overrides)
    missing=[k for k,v in values.items() if not v]
    if not os.getenv('NASHR_AUTH_PASSWORD'):missing.append('NASHR_AUTH_PASSWORD')
    if (overrides or {}).get('META_INSTAGRAM_CONFIG_REVIEWED',os.getenv('META_INSTAGRAM_CONFIG_REVIEWED'))!='true':missing.append('META_INSTAGRAM_CONFIG_REVIEWED')
    for k in ['META_APP_ID','META_INSTAGRAM_CONFIG_ID']:
        if values[k] and not re.fullmatch(r'[0-9]{3,40}',values[k]):missing.append(k+':INVALID')
    u=urlsplit(values['META_INSTAGRAM_REDIRECT_URI'])
    if values['META_INSTAGRAM_REDIRECT_URI'] and (u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path!=BASE+'/callback'):
        missing.append('META_INSTAGRAM_REDIRECT_URI:INVALID')
    if values['NASHR_CONNECTION_ENCRYPTION_KEY']:
        try:Fernet(values['NASHR_CONNECTION_ENCRYPTION_KEY'].encode())
        except (ValueError,TypeError):missing.append('NASHR_CONNECTION_ENCRYPTION_KEY:INVALID')
    values['missing']=missing
    values['fingerprint']=digest(json.dumps(values,sort_keys=True))
    return values

async def configuration_for(session,required=False):
    from app.infrastructure.database.models import PlatformAppSettingsModel
    row=await session.get(PlatformAppSettingsModel,'instagram')
    overrides=None
    if row:
        try:
            from app.application.managed_connections import key
            overrides=json.loads(key().decrypt(row.ciphertext.encode()))
        except (ValueError,InvalidToken):
            c=configuration();c['missing'].append('SAVED_APP_SETTINGS_UNREADABLE')
            if required:raise ValueError('تعذر فتح إعداد تطبيق Meta المحفوظ؛ لم نعد إلى إعداد قديم.') from None
            return c
    c=configuration(overrides)
    if required and c['missing']:raise ValueError('ربط Instagram غير مهيأ. راجع إعداد تطبيق Meta في لوحة الاتصالات.')
    return c

def cipher(c):return Fernet(c['NASHR_CONNECTION_ENCRYPTION_KEY'].encode())

def connection_payload(row,c):
    if not row:return None
    stale=row.config_hash!=c['fingerprint']
    expired=row.token_expires_at is not None and row.token_expires_at<=now()
    return {'account_id':row.account_id,'username':row.username,'connected_at':row.connected_at.isoformat(),
        'expires_at':row.token_expires_at.isoformat() if row.token_expires_at else None,
        'state':'DISABLED' if row.enabled is False else 'RECONNECT_REQUIRED' if stale or expired or row.last_check_ok is False else 'CONNECTED_AT_LAST_CHECK',
        'enabled':row.enabled,'client_business_id':row.client_business_id,'token_type':row.token_type,'last_check_at':row.last_check_at.isoformat() if row.last_check_at else None,'last_check_ok':row.last_check_ok,'last_check_error':row.last_check_error,
        'scopes':row.scopes,'execution_authorized':False,
        'caveat':'آخر تحقق وقت الربط فقط؛ قد تُلغى الصلاحية خارج Nashr. لا موصل نشر أو إذن تنفيذ من هذا الربط.'}

async def status(session,session_token,browser):
    c=await configuration_for(session);row=await session.get(Connection,1) if session_token else None
    pending=None
    if browser:
        flow=(await session.execute(select(Flow).where(Flow.browser_hash==digest(browser),Flow.session_hash==digest(session_token),Flow.expires_at>now(),Flow.config_hash==c['fingerprint'],Flow.token_ciphertext.is_not(None)))).scalars().first()
        if flow:pending={'accounts':flow.accounts,'expires_at':flow.expires_at.isoformat()}
    return {'configured':not c['missing'],'missing_configuration':c['missing'],'connection':connection_payload(row,c),'pending':pending,
        'execution_authorized':False,'source':SOURCE,'flow':'META_UNIFIED_LOGIN',
        'requirements':['إعداد تطبيق Meta ومحفظة أعمال ومعرف إعداد الدخول وعنوان العودة أولاً.','حساب Instagram احترافي وصلاحيات التطبيق المطلوبة؛ لا تحويل حساب تلقائي.','يدخل المستخدم لدى Meta من جهازه، ولا يشارك كلمة المرور مع Nashr.','الربط وحده لا ينشر ولا يغير اختيار توزيع أو جدول.']}

async def begin(session,session_token):
    c=await configuration_for(session,True);state=secrets.token_urlsafe(32);browser=secrets.token_urlsafe(32)
    await session.execute(delete(Flow).where(Flow.expires_at<=now()))
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    # One active handoff per owner session. Never touch an existing connection.
    await session.execute(delete(Flow).where(Flow.session_hash==digest(session_token)))
    session.add(Flow(id=digest(state),session_hash=digest(session_token),browser_hash=digest(browser),config_hash=c['fingerprint'],expires_at=now()+timedelta(minutes=10),consumed=False,accounts=[],scopes=[]))
    await session.commit()
    url='https://www.facebook.com/dialog/oauth?'+urlencode({'client_id':c['META_APP_ID'],'config_id':c['META_INSTAGRAM_CONFIG_ID'],'redirect_uri':c['META_INSTAGRAM_REDIRECT_URI'],'response_type':'code','prompt':'login','state':state})
    return url,browser

async def _json(client,url,**kwargs):
    try:
        response=await client.get(url,**kwargs)
        response.raise_for_status();data=response.json()
        if not isinstance(data,dict) or data.get('error'):raise ValueError()
        return data
    except (httpx.HTTPError,ValueError,TypeError):
        # Do not return upstream diagnostics, tokens or request URLs.
        raise ValueError('تعذر التحقق من ربط Meta. لم يتغير الربط السابق؛ ابدأ محاولة جديدة.') from None

async def exchange(code,c):
    # Exact fixed hosts; redirects disabled, tokens never reach a frontend response.
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        data=await _json(client,'https://graph.facebook.com/v27.0/oauth/access_token',params={'client_id':c['META_APP_ID'],'client_secret':c['META_APP_SECRET'],'redirect_uri':c['META_INSTAGRAM_REDIRECT_URI'],'code':code})
        token=data.get('access_token')
        if not isinstance(token,str) or not token or len(token)>16000:raise ValueError('لم يرجع Meta رمز وصول صالحاً.')
        debug=await _json(client,'https://graph.facebook.com/v27.0/debug_token',params={'input_token':token,'access_token':c['META_APP_ID']+'|'+c['META_APP_SECRET']})
        info=debug.get('data',{})
        scopes=info.get('scopes',[])
        if not isinstance(scopes,list) or not all(isinstance(s,str) for s in scopes) or info.get('is_valid') is not True or str(info.get('app_id'))!=c['META_APP_ID'] or not REQUIRED.issubset(scopes):
            raise ValueError('صلاحيات Meta أو التطبيق لا تطابق متطلبات الربط. لم يُربط أي حساب.')
        headers={'Authorization':'Bearer '+token}
        business=await _json(client,'https://graph.facebook.com/v27.0/me',params={'fields':'client_business_id'},headers=headers)
        business_id=str(business.get('client_business_id',''))
        if not re.fullmatch(r'[0-9]{1,100}',business_id):raise ValueError('لم يرجع Meta معرف النشاط التجاري للربط. لم يتغير الحساب السابق.')
        data=await _json(client,'https://graph.facebook.com/v27.0/me/assigned_instagram_accounts',params={'fields':'id,username','limit':100},headers=headers)
        accounts=data.get('data')
        paging=data.get('paging',{})
        if not isinstance(paging,dict) or paging.get('next'):raise ValueError('قائمة الحسابات غير مكتملة. حدّد أصولاً أقل لدى Meta ثم أعد الربط.')
        if not isinstance(accounts,list) or not accounts or len(accounts)>100:raise ValueError('لم يرجع Meta حساب Instagram احترافياً متاحاً. لم يتغير حسابك.')
        clean=[]
        for a in accounts:
            if not isinstance(a,dict) or not re.fullmatch(r'[0-9]{1,100}',str(a.get('id',''))) or not re.fullmatch(r'[A-Za-z0-9_.]{1,100}',str(a.get('username',''))):raise ValueError('بيانات الحساب غير صالحة.')
            clean.append({'account_id':str(a['id']),'username':a['username']})
        expires=[]
        for key in ['expires_at','data_access_expires_at']:
            value=info.get(key)
            if isinstance(value,int) and value>0:expires.append(datetime.fromtimestamp(value,timezone.utc))
        expiry=min(expires) if expires else None
        if expiry and expiry<=now():raise ValueError('انتهت صلاحية Meta. أعد الربط.')
        return token,clean,sorted(set(scopes)),expiry,business_id

async def finish(session,session_token,browser,state,code,error=False):
    c=await configuration_for(session,True)
    if not browser or not state or len(state)>256:raise ValueError('جلسة الربط غير صالحة أو انتهت. ابدأ من Nashr.')
    result=await session.execute(update(Flow).where(Flow.id==digest(state),Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.consumed.is_(False)).values(consumed=True).returning(Flow.id))
    flow_id=result.scalar_one_or_none();await session.commit()
    if not flow_id:raise ValueError('جلسة الربط مستخدمة أو منتهية أو تخص متصفحاً آخر.')
    if error or not code or len(code)>8000:raise ValueError('أُلغي ربط Meta أو لم يكتمل. لم يتغير الربط السابق.')
    token,accounts,scopes,expiry,business_id=await exchange(code,c)
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    flow=await session.get(Flow,flow_id)
    if flow is None or flow.expires_at<=now():raise ValueError('انتهت جلسة الربط أو ألغيت. أعد المحاولة.')
    flow.token_ciphertext=cipher(c).encrypt(token.encode()).decode();flow.accounts=accounts;flow.scopes=scopes;flow.token_expires_at=expiry;flow.client_business_id=business_id
    await session.commit()

async def select_account(session,session_token,browser,account_id):
    c=await configuration_for(session,True)
    if not browser:raise ValueError('انتهت معاينة الحسابات. أعد الربط.')
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    flow=(await session.execute(select(Flow).where(Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)).with_for_update())).scalars().first()
    if not flow:raise ValueError('انتهت معاينة الحسابات. أعد الربط.')
    account=next((a for a in flow.accounts if a['account_id']==account_id),None)
    if not account:raise ValueError('اختر حساباً من قائمة Meta المعروضة فقط.')
    if flow.token_expires_at and flow.token_expires_at<=now():raise ValueError('انتهت صلاحية الرمز. أعد الربط.')
    try:cipher(c).decrypt(flow.token_ciphertext.encode())
    except InvalidToken:raise ValueError('تعذر قراءة الرمز المحمي. أعد الربط.') from None
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    row=await session.get(Connection,1)
    if not row:row=Connection(id=1);session.add(row)
    row.client_business_id=flow.client_business_id;row.token_type='BUSINESS_INTEGRATION_SYSTEM_USER';row.enabled=True;row.last_check_at=now();row.last_check_ok=True;row.last_check_error=None
    row.account_id=account['account_id'];row.username=account['username'];row.token_ciphertext=flow.token_ciphertext;row.scopes=flow.scopes;row.config_hash=c['fingerprint'];row.token_expires_at=flow.token_expires_at;row.connected_at=now()
    await session.execute(delete(Flow).where(Flow.session_hash==digest(session_token)))
    await session.commit()

async def disconnect(session,session_token):
    # Local removal only. No remote revocation claim or change to Meta account.
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    await session.execute(delete(Connection).where(Connection.id==1))
    await session.execute(delete(Flow))
    await session.commit()

async def verify_saved_connection(session,*,provider_factory=None):
    """Explicit read-only Meta check. Caller must authenticate the owner first."""
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    c=await configuration_for(session,True)
    row=await session.get(Connection,1,populate_existing=True)
    if row is None:raise ValueError('لا يوجد حساب Instagram محفوظ للتحقق منه.')
    if row.config_hash!=c['fingerprint']:raise ValueError('تغير إعداد التطبيق. أعد ربط الحساب دون استخدام الإعداد السابق.')
    if row.token_expires_at and row.token_expires_at<=now():raise ValueError('انتهت الصلاحية المسجلة. أعد ربط الحساب.')
    try:token=cipher(c).decrypt(row.token_ciphertext.encode()).decode()
    except InvalidToken:raise ValueError('تعذر فتح الرمز المحمي. أعد ربط الحساب.') from None
    from app.adapters.publishing.instagram import InstagramPublisher,InstagramProviderError
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        provider=(provider_factory or InstagramPublisher)(client=client,token=token,account_id=row.account_id)
        try:
            facts=await provider.verify_account(app_access_token=c['META_APP_ID']+'|'+c['META_APP_SECRET'],expected_app_id=c['META_APP_ID'])
            if row.client_business_id and row.client_business_id!=facts['client_business_id']:raise InstagramProviderError('INSTAGRAM_BUSINESS_MISMATCH')
        except InstagramProviderError as exc:
            row.last_check_at=now();row.last_check_ok=False;row.last_check_error=exc.code;await session.commit()
            raise ValueError('تعذر التحقق من صلاحية حساب Instagram المحفوظ. لا نشر أو تبديل للحساب؛ راجع الربط ثم أعد التحقق.') from None
    row.client_business_id=facts['client_business_id'];row.username=facts['username'];row.scopes=facts['scopes'];row.token_type='BUSINESS_INTEGRATION_SYSTEM_USER'
    checked_expiry=datetime.fromtimestamp(facts['expires_at'],timezone.utc) if facts['expires_at'] else None
    # Unknown expiry cannot erase a previously recorded earlier deadline.
    known=[value for value in (row.token_expires_at,checked_expiry) if value is not None]
    row.token_expires_at=min(known) if known else None
    row.last_check_at=now();row.last_check_ok=True;row.last_check_error=None
    await session.commit();return connection_payload(row,c)

async def set_connection_enabled(session,enabled):
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    row=await session.get(Connection,1,populate_existing=True)
    if row is None:raise ValueError('لا يوجد حساب Instagram محفوظ.')
    if enabled:
        c=await configuration_for(session,True)
        if row.config_hash!=c['fingerprint'] or row.last_check_ok is not True or row.last_check_at is None or row.last_check_at<now()-timedelta(minutes=5) or row.token_expires_at and row.token_expires_at<=now():raise ValueError('تحقق من الحساب الآن قبل إعادة تفعيله محلياً. لن نطلب صلاحيات جديدة.')
    row.enabled=enabled;await session.commit()
