"""Instagram Login connection only. No Facebook fallback or publishing."""
import json,re,secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode,urlsplit
import httpx
from sqlalchemy import select,delete,text
from cryptography.fernet import InvalidToken
from app.application.managed_connections import key
from app.application.instagram_oauth import digest
from app.infrastructure.database.models import InstagramDirectOAuthFlowModel as Flow,InstagramDirectConnectionModel as Connection,PlatformAppSettingsModel

BASE='/api/connections/instagram-direct'
COOKIE='nashr_instagram_direct_oauth'
SOURCE='https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login/'
SCOPES=frozenset({'instagram_business_basic','instagram_business_content_publish'})
ID=re.compile(r'^[0-9]{1,100}$')

def now():return datetime.now(timezone.utc)

class DirectFailure(ValueError):
    def __init__(self,reason):
        allowed={'SESSION','CANCELLED','CONFIGURATION','TOKEN_EXCHANGE','PERMISSIONS','IDENTITY','EXPIRY','PROVIDER','CONFIG_CHANGED'}
        self.reason=reason if reason in allowed else 'PROVIDER'
        super().__init__(self.reason)

async def lock(session):await session.execute(text('SELECT pg_advisory_xact_lock(606026)'))

async def configuration(session,required=False):
    row=await session.get(PlatformAppSettingsModel,'instagram_direct');c={}
    if row:
        try:
            c=json.loads(key().decrypt(row.ciphertext.encode()))
            if not isinstance(c,dict):raise ValueError()
        except (InvalidToken,ValueError,TypeError):raise DirectFailure('CONFIGURATION') from None
    missing=[]
    for field in ['app_id','app_secret','redirect_uri']:
        if not isinstance(c.get(field),str) or not c[field]:missing.append(field)
    if c.get('app_id') and not ID.fullmatch(c['app_id']):missing.append('app_id')
    if c.get('direct_login_reviewed') is not True:missing.append('direct_login_reviewed')
    u=urlsplit(c.get('redirect_uri',''))
    if c.get('redirect_uri') and (u.scheme!='https' or not u.hostname or u.path!=BASE+'/callback' or u.query or u.fragment or u.username or u.password):missing.append('redirect_uri')
    try:key()
    except ValueError:missing.append('encryption_key')
    c['missing']=missing;c['fingerprint']=digest(json.dumps(c,sort_keys=True))
    if required and missing:raise DirectFailure('CONFIGURATION')
    return c

def payload(row,c):
    if not row:return None
    invalid=row.config_hash!=c['fingerprint'] or row.token_expires_at<=now() or row.last_check_ok is False
    return dict(account_id=row.account_id,username=row.username,token_type='INSTAGRAM_USER',enabled=row.enabled,state='DISABLED' if not row.enabled else 'RECONNECT_REQUIRED' if invalid else 'CONNECTED_AT_LAST_CHECK',expires_at=row.token_expires_at.isoformat(),last_check_at=row.last_check_at.isoformat() if row.last_check_at else None,scopes=row.scopes,execution_authorized=False)

async def status(session,session_token,browser):
    c=await configuration(session);row=await session.get(Connection,1) if session_token else None;pending=None
    if session_token and browser:
        flow=(await session.execute(select(Flow).where(Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)))).scalars().first()
        if flow:pending={'accounts':flow.accounts,'expires_at':flow.expires_at.isoformat()}
    return dict(configured=not c['missing'],missing_configuration=c['missing'],connection=payload(row,c),pending=pending,flow='INSTAGRAM_LOGIN',source=SOURCE,execution_authorized=False)

async def begin(session,session_token):
    c=await configuration(session,True);state=secrets.token_urlsafe(32);browser=secrets.token_urlsafe(32)
    await lock(session)
    await session.execute(delete(Flow).where((Flow.expires_at<=now()) | (Flow.session_hash==digest(session_token))))
    session.add(Flow(id=digest(state),session_hash=digest(session_token),browser_hash=digest(browser),config_hash=c['fingerprint'],expires_at=now()+timedelta(minutes=10),consumed=False,accounts=[]))
    await session.commit()
    return 'https://www.instagram.com/oauth/authorize?'+urlencode(dict(client_id=c['app_id'],redirect_uri=c['redirect_uri'],response_type='code',scope=','.join(sorted(SCOPES)),state=state,enable_fb_login='false')),browser

async def request_json(client,method,url,**kwargs):
    try:
        response=await client.request(method,url,follow_redirects=False,**kwargs);d=response.json()
        if response.status_code!=200 or not isinstance(d,dict) or d.get('error'):raise ValueError()
        return d
    except (httpx.HTTPError,ValueError,TypeError):raise DirectFailure('PROVIDER') from None

def single(d):
    # Meta documents data wrappers for exchange/me. Also accept the same
    # documented object fields unwrapped, never multiple identities.
    if 'data' in d:
        rows=d['data']
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):raise DirectFailure('IDENTITY')
        return rows[0]
    return d

def identity(d):
    d=single(d);uid=d.get('user_id');username=d.get('username');scoped=d.get('id')
    if not isinstance(scoped,str) or not ID.fullmatch(scoped) or not isinstance(uid,str) or not ID.fullmatch(uid) or not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,100}',username):raise DirectFailure('IDENTITY')
    return dict(account_id=uid,username=username,app_scoped_id=scoped)

async def read_identity(client,token):
    d=await request_json(client,'GET','https://graph.instagram.com/v27.0/me',headers={'Authorization':'Bearer '+token},params={'fields':'id,user_id,username'})
    return identity(d)

async def exchange(code,c):
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        try:
            d=single(await request_json(client,'POST','https://api.instagram.com/oauth/access_token',data=dict(client_id=c['app_id'],client_secret=c['app_secret'],grant_type='authorization_code',redirect_uri=c['redirect_uri'],code=code)))
        except DirectFailure:raise DirectFailure('TOKEN_EXCHANGE') from None
        token=d.get('access_token');uid=d.get('user_id');permissions=d.get('permissions')
        if not isinstance(token,str) or not token or len(token)>16000 or not isinstance(uid,str) or not ID.fullmatch(uid):raise DirectFailure('TOKEN_EXCHANGE')
        scopes=permissions.split(',') if isinstance(permissions,str) else permissions
        if not isinstance(scopes,list) or not all(isinstance(x,str) for x in scopes) or not SCOPES.issubset(scopes):raise DirectFailure('PERMISSIONS')
        # This token is obtained only by a state-bound code exchange with the
        # configured Instagram client ID/secret. Never accept pasted tokens.
        long=await request_json(client,'GET','https://graph.instagram.com/access_token',params=dict(grant_type='ig_exchange_token',client_secret=c['app_secret'],access_token=token))
        token=long.get('access_token');seconds=long.get('expires_in')
        if not isinstance(token,str) or not token or len(token)>16000 or long.get('token_type','').lower()!='bearer' or type(seconds) is not int or seconds<=0 or seconds>60*86400:raise DirectFailure('EXPIRY')
        account=await read_identity(client,token)
        if account['app_scoped_id']!=uid:raise DirectFailure('IDENTITY')
        return token,account,sorted(set(scopes)),now()+timedelta(seconds=seconds)

async def finish(session,session_token,browser,state,code,error=False):
    c=await configuration(session,True)
    if not browser or not state or len(state)>256:raise DirectFailure('SESSION')
    await lock(session)
    flow=(await session.execute(select(Flow).where(Flow.id==digest(state),Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.consumed.is_(False)).with_for_update())).scalar_one_or_none()
    if not flow:raise DirectFailure('SESSION')
    flow.consumed=True;await session.commit()
    if error or not code or len(code)>8000:raise DirectFailure('CANCELLED')
    token,account,scopes,expiry=await exchange(code,c)
    await lock(session);flow=await session.get(Flow,digest(state),populate_existing=True)
    if not flow or flow.expires_at<=now() or flow.config_hash!=(await configuration(session,True))['fingerprint']:raise DirectFailure('CONFIG_CHANGED')
    flow.accounts=[account];flow.token_ciphertext=key().encrypt(json.dumps(dict(token=token,account=account,scopes=scopes,expires_at=expiry.isoformat())).encode()).decode();await session.commit()

async def selected_facts(c,entry):
    if datetime.fromisoformat(entry['expires_at'])<=now():raise DirectFailure('EXPIRY')
    if not SCOPES.issubset(entry['scopes']):raise DirectFailure('PERMISSIONS')
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:account=await read_identity(client,entry['token'])
    if account!=entry['account']:raise DirectFailure('IDENTITY')
    return account

async def select_account(session,session_token,browser,account_id):
    if not browser:raise DirectFailure('SESSION')
    await lock(session);c=await configuration(session,True)
    flow=(await session.execute(select(Flow).where(Flow.session_hash==digest(session_token),Flow.browser_hash==digest(browser),Flow.config_hash==c['fingerprint'],Flow.expires_at>now(),Flow.token_ciphertext.is_not(None)).with_for_update())).scalars().first()
    if not flow:raise DirectFailure('SESSION')
    try:
        entry=json.loads(key().decrypt(flow.token_ciphertext.encode()));account=await selected_facts(c,entry)
    except (InvalidToken,ValueError,KeyError,TypeError):raise DirectFailure('IDENTITY') from None
    if account['account_id']!=account_id:raise DirectFailure('IDENTITY')
    row=await session.get(Connection,1)
    if not row:row=Connection(id=1);session.add(row)
    row.account_id=account_id;row.username=account['username'];row.token_ciphertext=key().encrypt(json.dumps(entry).encode()).decode();row.scopes=entry['scopes'];row.config_hash=c['fingerprint'];row.token_expires_at=datetime.fromisoformat(entry['expires_at']);row.connected_at=now();row.last_check_at=now();row.last_check_ok=True;row.enabled=True
    await session.execute(delete(Flow).where(Flow.session_hash==digest(session_token)));await session.commit()

async def verify_saved_connection(session):
    await lock(session);c=await configuration(session,True);row=await session.get(Connection,1,populate_existing=True)
    if not row or row.config_hash!=c['fingerprint'] or row.token_expires_at<=now():raise DirectFailure('CONFIGURATION')
    try:
        entry=json.loads(key().decrypt(row.token_ciphertext.encode()));account=await selected_facts(c,entry)
        if account['account_id']!=row.account_id or account['username']!=row.username:raise DirectFailure('IDENTITY')
    except (InvalidToken,ValueError,KeyError,TypeError):
        row.last_check_ok=False;row.last_check_at=now();await session.commit();raise DirectFailure('IDENTITY') from None
    row.last_check_ok=True;row.last_check_at=now();await session.commit();return payload(row,c)

async def set_connection_enabled(session,enabled):
    await lock(session);c=await configuration(session,True);row=await session.get(Connection,1,populate_existing=True)
    if not row:raise DirectFailure('CONFIGURATION')
    if enabled and (row.config_hash!=c['fingerprint'] or row.token_expires_at<=now() or row.last_check_ok is not True or not row.last_check_at or row.last_check_at<now()-timedelta(minutes=5)):raise DirectFailure('IDENTITY')
    row.enabled=enabled;await session.commit()

async def disconnect(session,session_token):
    await lock(session);await session.execute(delete(Connection));await session.execute(delete(Flow));await session.commit()
