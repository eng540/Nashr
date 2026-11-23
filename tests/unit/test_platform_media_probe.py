import io
import pytest
from PIL import Image
from app.domain.platform_media_probe import inspect_media,media_findings


def test_real_image_probe_does_not_convert_or_overstate_eligibility():
    stream=io.BytesIO();Image.new('RGB',(640,800)).save(stream,format='JPEG');data=stream.getvalue()
    info=inspect_media(data,'IMAGE','image/jpeg')
    assert info=={'format':'JPEG','width':640,'height':800,'size_bytes':len(data)}
    blockers,pending=media_findings('instagram','IMAGE',info)
    assert not blockers and pending
    assert data==stream.getvalue()
    bad=dict(info,format='PNG',width=100,height=800,size_bytes=8_000_001)
    assert len(media_findings('instagram','IMAGE',bad)[0])==3


def test_video_rules_remain_partial_even_when_measured_fields_pass():
    info={'width':1080,'height':1920,'size_bytes':100,'video_codec':'h264','pixel_format':'yuv420p','field_order':'progressive','duration_seconds':30,'fps':30,'video_bitrate':2_000_000,'audio':[]}
    blockers,pending=media_findings('instagram','VIDEO',info)
    assert not blockers and len(pending)>=3
    bad={**info,'video_codec':'vp9','fps':120,'duration_seconds':1,'video_bitrate':26_000_000}
    assert len(media_findings('instagram','VIDEO',bad)[0])==4


def test_unreadable_image_never_passes():
    with pytest.raises(Exception):inspect_media(b'not-an-image','IMAGE','image/jpeg')


def test_real_mp4_probe_extracts_streams_and_missing_binary_is_not_pass(tmp_path,monkeypatch):
    import shutil,subprocess
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):pytest.skip('local media binaries unavailable')
    file=tmp_path/'synthetic.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x400:r=30','-t','3','-an','-c:v','libx264','-pix_fmt','yuv420p','-y',str(file)],check=True,timeout=15)
    data=file.read_bytes();info=inspect_media(data,'VIDEO','video/mp4')
    assert info['width']==320 and info['height']==400 and info['video_codec']=='h264' and info['fps']==30 and info['duration_seconds']==3
    assert not media_findings('instagram','VIDEO',info)[0]
    def broken(*a,**kw):raise FileNotFoundError()
    monkeypatch.setattr(subprocess,'run',broken)
    with pytest.raises(FileNotFoundError):inspect_media(data,'VIDEO','video/mp4')
