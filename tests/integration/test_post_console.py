from fastapi.responses import HTMLResponse
import pytest

from app.api.routes import posts_console


@pytest.mark.asyncio
async def test_dedicated_posts_console_is_separate_from_library() -> None:
    response = await posts_console()
    assert isinstance(response, HTMLResponse)
    assert "مصنع المنشورات" in response.body.decode("utf-8")
    assert 'id="start-production"' in response.body.decode("utf-8")
    assert 'id="bank-title"' in response.body.decode("utf-8")
    assert 'id="editor"' in response.body.decode("utf-8")
