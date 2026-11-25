"""Optional password gate for the whole Nashr deployment.

When NASHR_AUTH_PASSWORD is set, every route except /health, /login and the
login endpoint requires a valid session cookie. When it is unset (local
development and tests), the gate stays open and behavior is unchanged.

Design notes:
- Session cookie: HMAC-signed token, HttpOnly, Secure, SameSite=Lax, 7 days.
  SameSite=Lax means browsers never attach the cookie to cross-site POSTs,
  which covers CSRF for the mutation endpoints; no token appears in URLs or
  in the frontend bundle.
- Browser navigation (GET with Accept: text/html) is redirected to /login;
  API callers receive a JSON 401.
- Credentials come from the environment only (NASHR_AUTH_USERNAME,
  NASHR_AUTH_PASSWORD, optional NASHR_SESSION_SECRET for key separation).
"""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

SESSION_COOKIE = "nashr_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 3600
_OPEN_PATHS = frozenset({"/health", "/terms", "/privacy", "/login", "/api/auth/login", "/tiktokQDsoHAsAIEswE2q0vxreoi4iWCJbhDsS.txt", "/tiktokePPmBzm3Ej1QWBVM7rVXy8eiIbCCGpJj.txt"})

LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nashr - تسجيل الدخول</title>
<style>
  body { font-family: system-ui, sans-serif; background: #0f1115; color: #e7e9ee;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
  form { background: #1a1d24; padding: 2rem; border-radius: 12px; width: 320px;
         display: flex; flex-direction: column; gap: 0.9rem; }
  h1 { font-size: 1.2rem; margin: 0 0 0.5rem; }
  input { padding: 0.6rem; border-radius: 8px; border: 1px solid #333a45;
          background: #0f1115; color: #e7e9ee; }
  button { padding: 0.7rem; border: 0; border-radius: 8px; background: #6d5ae0;
           color: #fff; font-size: 1rem; cursor: pointer; }
  .error { color: #ff7b7b; font-size: 0.85rem; }
</style>
</head>
<body>
<form method="post" action="/api/auth/login">
  <h1>Nashr - تسجيل الدخول</h1>
  __ERROR__
  <input name="username" autocomplete="username" placeholder="اسم المستخدم" required>
  <input name="password" type="password" autocomplete="current-password" placeholder="كلمة المرور" required>
  <button type="submit">دخول</button>
</form>
</body>
</html>"""


def auth_enabled() -> bool:
    return bool(os.getenv("NASHR_AUTH_PASSWORD"))


def _secret() -> bytes:
    secret = os.getenv("NASHR_SESSION_SECRET") or os.getenv("NASHR_AUTH_PASSWORD") or ""
    return secret.encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_token(username: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"u": username, "exp": int(time.time()) + SESSION_MAX_AGE_SECONDS}).encode("utf-8")
    ).decode("ascii")
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload)):
        return False
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return False
    return isinstance(data.get("exp"), int) and data["exp"] > int(time.time())


def _credentials_valid(username: str, password: str) -> bool:
    expected_user = os.getenv("NASHR_AUTH_USERNAME", "admin")
    expected_password = os.getenv("NASHR_AUTH_PASSWORD", "")
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_password)


def _set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        issue_token(username),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect browsers to /login and reject unauthenticated API calls."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == '/instagram-media':
            request.state.instagram_media_capability=request.query_params.get('capability','')
            request.scope['query_string']=b''
            response=await call_next(request)
            response.headers['Cache-Control']='no-store'
            response.headers['Referrer-Policy']='no-referrer'
            return response
        if request.url.path in {'/api/connections/instagram/callback','/api/connections/instagram-page/callback','/api/connections/instagram-direct/callback','/api/connections/facebook/callback','/api/connections/tiktok/callback','/api/connections/youtube/callback'}:
            # OAuth codes must not land in Uvicorn access-log query strings.
            request.state.instagram_oauth_query = dict(request.query_params)
            request.scope['query_string'] = b''

        if request.url.path.startswith('/api/connections'):
            if auth_enabled() and not verify_token(request.cookies.get(SESSION_COOKIE)):
                return JSONResponse({'detail':'Authentication required.'},status_code=401,headers={'Cache-Control':'no-store'})
            response=await call_next(request)
            response.headers['Cache-Control']='no-store'
            response.headers['Referrer-Policy']='no-referrer'
            return response
        if not auth_enabled():
            return await call_next(request)
        if request.url.path in _OPEN_PATHS:
            return await call_next(request)
        if verify_token(request.cookies.get(SESSION_COOKIE)):
            return await call_next(request)
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "Authentication required."}, status_code=401)


router = APIRouter(include_in_schema=False)


@router.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return HTMLResponse(LOGIN_PAGE_HTML.replace("__ERROR__", ""))


@router.post("/api/auth/login")
async def login(request: Request) -> Response:
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    if not _credentials_valid(username, password):
        return HTMLResponse(
            LOGIN_PAGE_HTML.replace("__ERROR__", '<p class="error">بيانات الدخول غير صحيحة.</p>'),
            status_code=401,
        )
    response = RedirectResponse("/console", status_code=303)
    _set_session_cookie(response, username)
    return response


@router.post("/api/auth/logout")
async def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
