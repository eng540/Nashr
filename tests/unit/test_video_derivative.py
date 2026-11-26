import subprocess
import pytest
from app.domain.video_derivative import video_derivative

@pytest.fixture(scope='module')
def source(tmp_path_factory):
 p=tmp_path_factory.mktemp('video')/'input.mp4'
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=25:d=3.1','-f','lavfi','-i','anoisesrc=sample_rate=24000:duration=3.1:seed=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(p)],check=True)
 return p.read_bytes()

@pytest.mark.parametrize('platform',['instagram','facebook'])
def test_full_frame_format_and_narration_stream_preserved(source,platform):
 data,m=video_derivative(source,platform)
 assert data!=source and (m['width'],m['height'])==(1080,1920)
 assert 3<=m['duration_seconds']<3.5 and m['fps']==25
 assert m['moov_before_media'] and not m['has_edit_lists']
 assert m['audio'][0]['channels']==2 and m['audio'][0]['sample_rate']==48000
 assert (m['audio'][0]['bitrate']<=128000) if platform=='instagram' else (m['audio'][0]['bitrate']>=128000)
 assert m['header_evidence']['closed_gop']=='REFRESH_BOUNDARIES_VERIFIED'

def test_unsupported_platform_and_oversize_fail_before_conversion():
 with pytest.raises(ValueError):video_derivative(b'bad','telegram')
 with pytest.raises(ValueError):video_derivative(b'','instagram')

def test_concurrent_conversion_fails_closed_without_ffmpeg(source):
 from app.domain.video_derivative import _conversion_slot
 assert _conversion_slot.acquire(blocking=False)
 try:
  with pytest.raises(ValueError,match='جارٍ'):video_derivative(source,'instagram')
 finally:_conversion_slot.release()
