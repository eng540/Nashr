import asyncio
import pytest
from app import main


@pytest.mark.asyncio
@pytest.mark.parametrize('fails',[False,True])
async def test_temporary_cleanup_runs_without_blocking_publishing(monkeypatch,caplog,fails):
    events=[]
    async def cleanup():
        events.append('cleanup')
        if fails:
            raise RuntimeError('private-candidate-must-not-be-logged')
        return 2
    async def instagram(): events.append('instagram')
    async def facebook(): events.append('facebook')
    async def due(*,limit):
        events.append('due')
        raise asyncio.CancelledError()
    monkeypatch.setattr('app.application.tiktok_oauth.cleanup_expired_flows',cleanup)
    monkeypatch.setattr('app.application.instagram_runtime.process_approved',instagram)
    monkeypatch.setattr('app.application.facebook_reel_runtime.process_approved',facebook)
    monkeypatch.setattr(main,'process_due_schedule_items',due)
    with pytest.raises(asyncio.CancelledError):
        await main.run_schedule_trigger()
    assert events==['cleanup','instagram','facebook','due']
    assert 'private-candidate' not in caplog.text
    assert ('TIKTOK_TEMPORARY_FLOW_CLEANUP_FAILED' in caplog.text)==fails
