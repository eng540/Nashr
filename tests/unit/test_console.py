from starlette.responses import HTMLResponse

from app.api.routes import console, publishing_console


async def test_console_is_library_workspace() -> None:
    response = await console()
    body = response.body.decode()
    assert isinstance(response, HTMLResponse)
    assert "مكتبة الكتب" in body or "مكتبة Nashr" in body
    assert "فتح الكتاب" in body
    assert "رفع الكتاب" in body
    assert "/sources/" in body
    assert "/discovery/status" in body
    assert 'id="start-discovery-btn"' in body
    assert 'id="discovery-status"' in body
    assert "post-bank-section" not in body
    assert "scheduling-section" not in body
    assert 'id="draft-content"' not in body
    assert 'id="publish-btn"' not in body
    assert 'href="/publishing"' in body
    assert "scrollIntoView" not in body


async def test_publishing_workspace_is_separate() -> None:
    response = await publishing_console()
    body = response.body.decode()
    assert isinstance(response, HTMLResponse)
    assert "مساحة النشر" in body
    assert 'id="scheduling-section"' in body
    assert 'href="/console"' in body
    assert 'href="/posts/workspace"' in body
