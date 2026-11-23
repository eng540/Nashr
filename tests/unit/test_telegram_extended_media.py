import pytest
from app.adapters.publishing.telegram import TelegramPublisher
from tests.unit.test_telegram_publisher_media import FakeAsyncClient
from app.domain.telegram_media import media_request


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,mime,method,field', [
 ('DOCUMENT','application/octet-stream','sendDocument','document'),
 ('AUDIO','audio/mpeg','sendAudio','audio'),
 ('VOICE','audio/ogg','sendVoice','voice'),
 ('ANIMATION','image/gif','sendAnimation','animation'),
 ('VIDEO_NOTE','video/mp4','sendVideoNote','video_note'),
 ('STICKER','image/webp','sendSticker','sticker'),
])
async def test_extended_media_methods(monkeypatch, kind,mime,method,field):
    FakeAsyncClient.calls=[]
    monkeypatch.setattr('app.adapters.publishing.telegram.httpx.AsyncClient',FakeAsyncClient)
    result=await TelegramPublisher(token='test-only').publish(destination='private-test', content='caption',media=b'bytes',media_mime_type=mime,media_kind=kind,media_filename='sample.bin')
    assert result.external_id=='4321'
    url,request=FakeAsyncClient.calls[0]
    assert url.endswith('/'+method)
    assert field in request['files']
    assert ('caption' not in request['data']) == (kind in {'VIDEO_NOTE','STICKER'})


def test_limits_and_method_mime_mismatch():
    with pytest.raises(ValueError,match='exceeds'):
        media_request('IMAGE','image/png',b'x'*(10*1024*1024+1))
    with pytest.raises(ValueError,match='MIME'):
        media_request('VOICE','image/png',b'x')


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="ffmpeg integration executable unavailable")
def test_video_note_and_sticker_geometry(tmp_path):
    import subprocess
    from app.domain.telegram_media import validate_special_media
    file=tmp_path/'note.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=green:s=128x128:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(file)],check=True)
    validate_special_media('VIDEO_NOTE','video/mp4',file.read_bytes())
    validate_special_media('ANIMATION','video/mp4',file.read_bytes())
    file2=tmp_path/'not-square.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=green:s=128x96:d=1','-c:v','libx264',str(file2)],check=True)
    with pytest.raises(ValueError,match='square'):
        validate_special_media('VIDEO_NOTE','video/mp4',file2.read_bytes())


@pytest.mark.parametrize("lossless", [False, True])
def test_webp_dimensions_without_optional_decoder(lossless):
    import io
    from PIL import Image
    from app.domain.telegram_media import webp_dimensions, validate_special_media
    output = io.BytesIO()
    Image.new("RGBA", (512, 480), (60, 90, 120, 100)).save(output, format="WEBP", lossless=lossless)
    assert webp_dimensions(output.getvalue()) == (512, 480)
    validate_special_media("STICKER", "image/webp", output.getvalue())
    with pytest.raises(ValueError):
        webp_dimensions(output.getvalue()[:-2])
