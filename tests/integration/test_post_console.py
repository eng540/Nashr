from fastapi.responses import HTMLResponse
import pytest

from app.api.routes import posts_console, router


@pytest.mark.asyncio
async def test_dedicated_posts_console_is_separate_from_library() -> None:
    response = await posts_console()
    assert isinstance(response, HTMLResponse)
    body = response.body.decode("utf-8")
    assert "مصنع المنشورات" in body
    assert 'id="start-production"' in body
    assert 'id="bank-title"' in body
    assert 'id="editor"' in body
    assert 'href="/console"' in body
    assert 'href="/console#scheduling-section"' in body
    assert 'id="next-to-scheduling"' in body
    assert 'التالي: بناء خطة النشر' in body
    assert "selected_post_ids" in body
    assert "APPROVED" in body
    workspace_routes = [route for route in router.routes if getattr(route, "endpoint", None) is posts_console]
    assert [route.path for route in workspace_routes] == ["/posts/workspace"]
    assert "selectedMaterials:new Set()" in body
    assert "selectedPosts:new Set()" in body
    assert "state.selectedMaterials.clear()" in body
    assert "state.selectedPosts.clear()" in body
    assert 'value="SELECTION">مواد أحددها بنفسي</option>' in body
