from starlette.responses import HTMLResponse

from app.api.routes import console


async def test_console_returns_html_response() -> None:
    response = await console()
    body = response.body.decode()
    assert isinstance(response, HTMLResponse)
    assert "Nashr Console" in body
    assert "/sources/" in body
    assert "/publications/" in body
