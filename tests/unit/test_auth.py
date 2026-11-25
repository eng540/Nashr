"""Tests for the optional deployment auth gate (app.api.auth)."""
import importlib
import os

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.auth as auth_module
import app.main as main_module


def _make_client(monkeypatch, **env):
    for key in ("NASHR_AUTH_PASSWORD", "NASHR_AUTH_USERNAME", "NASHR_SESSION_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    importlib.reload(auth_module)
    importlib.reload(main_module)
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="https://test")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_gate_open_when_password_unset(monkeypatch):
    async with _make_client(monkeypatch) as client:
        assert (await client.get("/health")).status_code == 200
        response = await client.get("/console")
        assert response.status_code == 303


@pytest.mark.anyio
async def test_health_stays_open_when_enabled(monkeypatch):
    async with _make_client(monkeypatch, NASHR_AUTH_PASSWORD="secret-pw") as client:
        assert (await client.get("/health")).status_code == 200


@pytest.mark.anyio
async def test_api_requires_session(monkeypatch):
    async with _make_client(monkeypatch, NASHR_AUTH_PASSWORD="secret-pw") as client:
        response = await client.get("/console", headers={"accept": "application/json"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required."


@pytest.mark.anyio
async def test_browser_redirected_to_login(monkeypatch):
    async with _make_client(monkeypatch, NASHR_AUTH_PASSWORD="secret-pw") as client:
        response = await client.get("/console", headers={"accept": "text/html"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert (await client.get("/login")).status_code == 200


@pytest.mark.anyio
async def test_login_success_sets_cookie_and_unlocks(monkeypatch):
    async with _make_client(monkeypatch, NASHR_AUTH_PASSWORD="secret-pw") as client:
        response = await client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "secret-pw"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "nashr_session" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert "samesite=lax" in response.headers["set-cookie"].lower()
        # Cookie is stored by the client; subsequent API call succeeds.
        assert (await client.get("/console")).status_code == 303


@pytest.mark.anyio
async def test_login_wrong_password_rejected(monkeypatch):
    async with _make_client(monkeypatch, NASHR_AUTH_PASSWORD="secret-pw") as client:
        response = await client.post(
            "/api/auth/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False
        )
        assert response.status_code == 401
        assert (await client.get("/console", headers={"accept": "application/json"})).status_code == 401


@pytest.mark.anyio
async def test_tampered_cookie_rejected(monkeypatch):
    async with _make_client(monkeypatch, NASHR_AUTH_PASSWORD="secret-pw") as client:
        client.cookies.set("nashr_session", "AAAA.forged")
        assert (await client.get("/console", headers={"accept": "application/json"})).status_code == 401


@pytest.mark.anyio
async def test_media_generation_kill_switch(monkeypatch):
    from app.application.media_gate import MediaGenerationDisabledError, ensure_media_generation_enabled

    monkeypatch.delenv("NASHR_MEDIA_GENERATION_DISABLED", raising=False)
    ensure_media_generation_enabled()
    monkeypatch.setenv("NASHR_MEDIA_GENERATION_DISABLED", "true")
    with pytest.raises(MediaGenerationDisabledError):
        ensure_media_generation_enabled()
