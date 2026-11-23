import subprocess
import pytest
from app.domain.telegram_live_photo import validate_live_motion


def motion_fixture(tmp_path, duration=1):
    path = tmp_path / 'motion.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10','-t',str(duration),'-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
    return path.read_bytes()


def test_motion_format_duration_and_size(tmp_path):
    data=motion_fixture(tmp_path)
    validate_live_motion(data)
    for invalid in [b'bad', data + b'x' * (10*1024*1024)]:
        with pytest.raises(ValueError): validate_live_motion(invalid)


@pytest.mark.asyncio
async def test_live_photo_adapter_uses_two_files_and_no_paid_fields(monkeypatch,tmp_path):
    from app.adapters.publishing.telegram import TelegramPublisher
    from tests.unit.test_telegram_publisher_media import FakeAsyncClient
    monkeypatch.setattr('app.adapters.publishing.telegram.httpx.AsyncClient',FakeAsyncClient)
    FakeAsyncClient.calls=[]
    result=await TelegramPublisher(token='fixture').publish(destination='private-fixture',content='Synthetic live photo',live_photo={'photo':b'png','photo_mime':'image/png','motion':motion_fixture(tmp_path)})
    url, request=FakeAsyncClient.calls[0]
    assert url.endswith('/sendLivePhoto')
    assert set(request['data'])=={'chat_id','caption','parse_mode'}
    assert set(request['files'])=={'photo','live_photo'}
    assert result.external_id
