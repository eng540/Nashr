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
    assert "async function renderSelectionCount(){".replace("async ","") not in body
    assert "function renderSelectionCount(){const button=$('schedule-from-selection');if(button)button.disabled=state.selectedPostIds.length===0;}" in body
    assert "async function hydrateSelection()" in body
    assert "await renderScheduleSelection();" in body
    assert "await request('/schedules/eligibility?'+params.toString())" in body
    assert "await request('/schedules',{method:'POST'" in body
