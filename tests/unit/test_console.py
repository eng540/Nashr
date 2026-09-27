from starlette.responses import HTMLResponse

from app.api.routes import console


async def test_console_returns_html_response() -> None:
    response = await console()
    body = response.body.decode()
    assert isinstance(response, HTMLResponse)
    assert "مساحة العمل" in body
    assert "/sources/" in body
    assert "/sources/{source_id}/discovery/status" in body or "/discovery/status" in body
    assert "/publications/" in body
    assert '<textarea id="draft-content"' in body
    assert 'id="drop-zone"' in body
    assert 'id="step-1"' in body
    assert 'id="progress-bar"' in body
    assert 'id="empty-library"' in body
