from fastapi.responses import HTMLResponse
import pytest

from app.api.routes import posts_console


@pytest.mark.asyncio
async def test_dedicated_posts_console_is_separate_from_library() -> None:
    response = await posts_console()
    assert isinstance(response, HTMLResponse)
    body = response.body.decode("utf-8")
    assert "مصنع المنشورات" in body
    assert 'id="start-production"' in body
    assert 'id="bank-title"' in body
    assert 'id="editor"' in body
