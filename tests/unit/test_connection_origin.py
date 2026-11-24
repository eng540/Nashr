"""TLS proxy handling must not turn untrusted forwarded headers into authority."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.api.auth import SESSION_COOKIE,issue_token
from app.api.instagram_connections import mutation_owner

def request(origin,host='nashr.example',extra=()):
    headers=[(b'host',host.encode()),(b'origin',origin.encode()),(b'cookie',(SESSION_COOKIE+'='+issue_token('owner')).encode()),*extra]
    return Request({'type':'http','scheme':'http','server':(host,80),'path':'/','headers':headers,'query_string':b''})

@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv('NASHR_AUTH_PASSWORD','test-owner');monkeypatch.setenv('NASHR_SESSION_SECRET','test-session-secret');monkeypatch.setenv('RAILWAY_PUBLIC_DOMAIN','nashr.example')

def test_configured_public_https_origin_behind_tls_proxy():
    assert mutation_owner(request('https://nashr.example'))

@pytest.mark.parametrize('origin',['https://evil.example','https://nashr.example.evil.example','https://nashr.example:444','https://nashr.example/path','https://nashr.example#fragment','https://attacker@nashr.example'])
def test_rejects_other_origins_and_non_origin_forms(origin):
    with pytest.raises(HTTPException):mutation_owner(request(origin))

def test_forwarded_headers_do_not_authorize_attacker():
    with pytest.raises(HTTPException):mutation_owner(request('https://evil.example',extra=[(b'x-forwarded-host',b'evil.example'),(b'x-forwarded-proto',b'https')]))
    with pytest.raises(HTTPException):mutation_owner(request('https://nashr.example',host='other.example'))

def test_absent_public_domain_requires_exact_request_scheme(monkeypatch):
    monkeypatch.delenv('RAILWAY_PUBLIC_DOMAIN')
    with pytest.raises(HTTPException):mutation_owner(request('https://nashr.example'))
    assert mutation_owner(request('http://nashr.example'))

def test_cross_site_fetch_is_rejected_even_with_matching_origin():
    with pytest.raises(HTTPException):mutation_owner(request('https://nashr.example',extra=[(b'sec-fetch-site',b'cross-site')]))
