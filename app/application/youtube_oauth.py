"""Read-only channel connection, isolated from upload and its authority."""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select, delete, text
from app.infrastructure.database.models import YouTubeConnectionModel as Connection, YouTubeOAuthFlowModel as Flow, PlatformAppSettingsModel
from app.application.managed_connections import key
from app.application.instagram_oauth import digest
from app.adapters.publishing import youtube_login as login

BASE = '/api/connections/youtube'
COOKIE = 'nashr_youtube_oauth'
SOURCE = 'https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps'
def now():
    return datetime.now(timezone.utc)
async def lock(s):
    await s.execute(text('SELECT pg_advisory_xact_lock(606031)'))

async def configuration(s, required=False):
    row = await s.get(PlatformAppSettingsModel, 'youtube_readonly')
    c = {}
    if row:
        try:
            c = json.loads(key().decrypt(row.ciphertext.encode()))
            if not isinstance(c, dict):
                raise ValueError()
        except (InvalidToken, ValueError):
            raise ValueError('تعذر فتح إعداد YouTube.') from None
    missing = [k for k in ['client_id', 'client_secret', 'redirect_uri'] if not isinstance(c.get(k), str) or not c[k]]
    u = urlsplit(c.get('redirect_uri', ''))
    if u.scheme != 'https' or not u.hostname or u.path != BASE + '/callback' or u.query or u.fragment or u.username or u.password:
        missing.append('redirect_uri')
    if c.get('oauth_status') not in {'TESTING', 'PUBLISHED'}:
        missing.append('oauth_status')
    if c.get('config_reviewed') is not True:
        missing.append('config_reviewed')
    if not os.getenv('NASHR_AUTH_PASSWORD'):
        missing.append('owner_auth')
    try:
        key()
    except ValueError:
        missing.append('encryption_key')
    c['missing'] = sorted(set(missing))
    c['fingerprint'] = digest(json.dumps(c, sort_keys=True))
    if required and missing:
        raise ValueError('أكمل إعداد عميل Google Web وتفعيل YouTube Data API والإذن للقراءة فقط.')
    return c

def payload(r, c):
    if not r:
        return None
    invalid = r.config_hash != c['fingerprint'] or r.last_check_ok is False
    # An expired access token can be renewed on an explicit verification, never
    # by a status GET or a scheduler. Its expiry alone is not lost authorization.
    return dict(channel_id=r.channel_id, title=r.title, scopes=r.scopes,
                state='DISABLED' if not r.enabled else 'RECONNECT_REQUIRED' if invalid else 'SAVED_NOT_LIVE',
                connected_at=r.connected_at.isoformat(), access_expires_at=r.token_expires_at.isoformat(),
                last_check_at=r.last_check_at.isoformat() if r.last_check_at else None,
                last_check_ok=r.last_check_ok, execution_authorized=False,
                caveat='قناة محفوظة من آخر تحقق، لا مراقبة مستمرة. القراءة فقط؛ لا رفع أو جدولة أو تعديل. التحقق الصريح يجدد رمز الوصول عند الحاجة دون تبديل القناة.')

async def status(s, owner, browser):
    c = await configuration(s)
    r = await s.get(Connection, 1) if owner else None
    pending = None
    if owner and browser:
        f = (await s.execute(select(Flow).where(Flow.session_hash == digest(owner), Flow.browser_hash == digest(browser), Flow.config_hash == c['fingerprint'], Flow.expires_at > now(), Flow.token_ciphertext.is_not(None)))).scalars().first()
        if f:
            pending = {'accounts': f.accounts, 'expires_at': f.expires_at.isoformat()}
    return dict(configured=not c['missing'], connection=payload(r, c), pending=pending,
                missing_configuration=c['missing'], scope=login.SCOPE, execution_authorized=False, source=SOURCE)

async def begin(s, owner):
    c = await configuration(s, True)
    state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    await lock(s)
    await s.execute(delete(Flow).where((Flow.session_hash == digest(owner)) | (Flow.expires_at <= now())))
    s.add(Flow(id=digest(state), session_hash=digest(owner), browser_hash=digest(browser), config_hash=c['fingerprint'], expires_at=now() + timedelta(minutes=10), consumed=False, accounts=[]))
    await s.commit()
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(dict(client_id=c['client_id'], response_type='code', scope=login.SCOPE, redirect_uri=c['redirect_uri'], state=state, access_type='offline', prompt='consent select_account', include_granted_scopes='false')), browser

def stamp(t, previous=None, testing=False):
    previous = previous or {}
    expiry = (now() + timedelta(seconds=t['refresh_expires_in'])).isoformat() if t.get('refresh_expires_in') else previous.get('refresh_expires_at')
    if testing:
        cap = previous.get('refresh_expires_at') or (now() + timedelta(days=7)).isoformat()
        expiry = min(expiry, cap) if expiry else cap
    return {**t, 'access_expires_at': (now() + timedelta(seconds=t['expires_in'])).isoformat(),
            'refresh_expires_at': expiry}

async def exchange(code, c):
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        t = await login.exchange(client, c, code)
        return t, await login.channels(client, t['access_token'])

async def finish(s, owner, browser, state, code, error=False):
    c = await configuration(s, True)
    if not browser or not state or len(state) > 256:
        raise ValueError('جلسة غير صالحة.')
    await lock(s)
    f = (await s.execute(select(Flow).where(Flow.id == digest(state), Flow.session_hash == digest(owner), Flow.browser_hash == digest(browser), Flow.config_hash == c['fingerprint'], Flow.expires_at > now(), Flow.consumed.is_(False)).with_for_update())).scalar_one_or_none()
    if not f:
        raise ValueError('جلسة منتهية أو مستخدمة.')
    f.consumed = True
    await s.commit()
    if error or not code or len(code) > 8000:
        raise ValueError('أُلغي الإذن.')
    t, accounts = await exchange(code, c)
    await lock(s)
    f = await s.get(Flow, digest(state), populate_existing=True)
    if not f or f.expires_at <= now() or (await configuration(s, True))['fingerprint'] != f.config_hash:
        raise ValueError('تغير الإعداد أثناء الربط.')
    f.token_ciphertext = key().encrypt(json.dumps(stamp(t, testing=c['oauth_status'] == 'TESTING')).encode()).decode()
    f.accounts = accounts
    await s.commit()

async def selected_facts(t):
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        return await login.channels(client, t['access_token'])

async def select_account(s, owner, browser, channel_id):
    if not browser:
        raise ValueError('أعد الربط.')
    await lock(s)
    c = await configuration(s, True)
    f = (await s.execute(select(Flow).where(Flow.session_hash == digest(owner), Flow.browser_hash == digest(browser), Flow.config_hash == c['fingerprint'], Flow.expires_at > now(), Flow.token_ciphertext.is_not(None)).with_for_update())).scalars().first()
    if not f or not any(x.get('channel_id') == channel_id for x in f.accounts):
        raise ValueError('اختر قناة من نتيجة Google فقط، لا من معرف مكتوب.')
    try:
        t = json.loads(key().decrypt(f.token_ciphertext.encode()))
        if datetime.fromisoformat(t['access_expires_at']) <= now():
            raise ValueError()
        found = [x for x in await selected_facts(t) if x['channel_id'] == channel_id]
        if len(found) != 1:
            raise ValueError()
    except (InvalidToken, ValueError, TypeError, KeyError):
        raise ValueError('تعذر التحقق من القناة المختارة. لم يتغير الربط السابق.') from None
    r = await s.get(Connection, 1)
    if not r:
        r = Connection(id=1)
        s.add(r)
    r.channel_id, r.title = channel_id, found[0]['title']
    r.token_ciphertext, r.config_hash = f.token_ciphertext, c['fingerprint']
    r.scopes = [login.SCOPE]
    r.token_expires_at = datetime.fromisoformat(t['access_expires_at'])
    r.connected_at = r.last_check_at = now()
    r.last_check_ok = r.enabled = True
    await s.execute(delete(Flow).where(Flow.session_hash == digest(owner)))
    await s.commit()

async def renewed(t, c):
    if t.get('refresh_expires_at') and datetime.fromisoformat(t['refresh_expires_at']) <= now():
        raise ValueError('Refresh expired')
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        return stamp(await login.refresh(client, c, t['refresh_token']), t, testing=c['oauth_status'] == 'TESTING')

async def verify(s):
    await lock(s)
    c = await configuration(s, True)
    r = await s.get(Connection, 1, populate_existing=True)
    if not r or not r.enabled or r.config_hash != c['fingerprint']:
        raise ValueError('أعد الربط، تغير إعداد التطبيق أو لم تُختر قناة.')
    try:
        t = json.loads(key().decrypt(r.token_ciphertext.encode()))
        if datetime.fromisoformat(t['access_expires_at']) <= now() + timedelta(seconds=60):
            t = await renewed(t, c)
            # Persist rotated refresh credentials even if the later identity read
            # fails, otherwise the former refresh token may already be invalid.
            r.token_ciphertext = key().encrypt(json.dumps(t).encode()).decode()
            r.token_expires_at = datetime.fromisoformat(t['access_expires_at'])
        matches = [x for x in await selected_facts(t) if x['channel_id'] == r.channel_id]
        if len(matches) != 1:
            raise ValueError()
    except (InvalidToken, ValueError, TypeError, KeyError):
        r.last_check_at, r.last_check_ok = now(), False
        await s.commit()
        raise ValueError('فشل تحقق YouTube. لا تبديل قناة أو رفع. قد تحتاج إعادة الإذن.') from None
    r.title, r.last_check_at, r.last_check_ok = matches[0]['title'], now(), True
    await s.commit()
    return payload(r, c)

async def disconnect(s, owner):
    await lock(s)
    await s.execute(delete(Connection))
    await s.execute(delete(Flow))
    await s.commit()

async def cleanup_expired_flows():
    from app.infrastructure.database.session import SessionFactory
    async with SessionFactory() as s:
        if not await s.scalar(text('SELECT pg_try_advisory_xact_lock(606031)')):
            return 0
        result = await s.execute(delete(Flow).where(Flow.expires_at <= now()))
        await s.commit()
        return result.rowcount
