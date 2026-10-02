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


async def test_library_discovery_controls_are_wired_without_cross_workspace_publish_coupling() -> None:
    response = await console()
    body = response.body.decode()
    assert 'function setBusy(v){' in body
    assert "$('publish-btn')" not in body
    assert "async function startDiscovery(sourceId)" in body
    assert "request('/sources/'+sourceId+'/discovery',{method:'POST'})" in body
    assert "$('start-discovery-btn').onclick=()=>{if(state.sourceId)startDiscovery(state.sourceId);};" in body
    assert "renderDiscoveryStatus(d);" in body
    assert "clearTimeout(state.pollTimer)" in body
    assert "if(!el)continue" in body


async def test_content_factory_approval_gates_next_transition() -> None:
    from app.api.post_console import NASHR_POSTS_HTML

    assert "const unapproved=selected.filter(id=>state.postMeta[id]?.status!=='APPROVED')" in NASHR_POSTS_HTML
    assert "unapproved.length>0" in NASHR_POSTS_HTML
    assert "اعتمد '+unapproved.length+' منشورًا محددًا" in NASHR_POSTS_HTML


async def test_publishing_selection_action_and_schedule_creation_are_wired() -> None:
    response = await publishing_console()
    body = response.body.decode()
    assert 'id="schedule-from-selection"' in body
    assert "async function openScheduleCreation()" in body
    assert "$('schedule-from-selection').onclick=openScheduleCreation;" in body
    assert "function renderSelectionCount()" in body
    assert "setText('post-selection-count',count+' محدد')" in body
    assert "async function hydrateSelection()" in body
    assert "await renderScheduleSelection();" in body
    assert "await request('/schedules/eligibility?'+params.toString())" in body
    assert "await request('/schedules',{method:'POST'" in body
    assert 'id="post-selection-count"' in body
    assert 'id="eligible-inventory"' in body
    assert 'id="eligible-posts"' in body
    assert "status','APPROVED'" in body
    assert "publication_state','ELIGIBLE'" in body
    assert "async function loadEligiblePosts()" in body
    assert "async function loadSourcesForEligibility()" in body
    assert "window.nashrPostSelection" not in body
    assert "function localDateTimeToUtcISOString(value,timeZone)" in body
    assert r"const match=/^(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2})$/.exec(value)" in body
    assert r"const match=/^(\\\\d{4})" not in body

async def test_content_factory_synchronizes_selected_post_state_before_actions() -> None:
    from app.api.post_console import NASHR_POSTS_HTML

    assert "async function syncSelectedPostMeta()" in NASHR_POSTS_HTML
    assert "await syncSelectedPostMeta();" in NASHR_POSTS_HTML
    assert "const unapproved=ids.filter(id=>state.postMeta[id]?.status!=='APPROVED')" in NASHR_POSTS_HTML
    assert "لا يمكن الانتقال إلى الجدولة قبل اعتماد جميع المنشورات المحددة" in NASHR_POSTS_HTML


async def test_publishing_console_has_no_dead_dom_references():
    """Guard against stale Post Bank references leaking into Publishing HTML."""
    from app.api.publishing_console import NASHR_PUBLISHING_HTML
    body = NASHR_PUBLISHING_HTML

    assert body.count("function renderSelectionCount") == 1,         "renderSelectionCount must have exactly one definition in Publishing HTML"

    dead_ids = [
        "post-bulk-approve",
        "post-bank-action-message",
        "post-bank-grid",
        "post-bank-summary",
        "post-page",
        "post-prev",
        "post-next",
    ]
    for dead in dead_ids:
        assert dead not in body, f"Publishing HTML must not reference '{dead}'"

    dead_functions = [
        "function renderPostBank",
        "function loadPostBank",
        "function showPostBankMessage",
        "function openPostEditor",
        "function togglePostSelection",
        "function selectedPost(",
    ]
    for dead in dead_functions:
        assert dead not in body, f"Dead function survived refactor: {dead}"

    assert "function renderEligiblePosts" in body
    assert "function loadEligiblePosts" in body
    assert "function showEligibleMessage" in body
    assert "function filterSelectionForScheduling" in body
    assert "function openScheduleCreation" in body
