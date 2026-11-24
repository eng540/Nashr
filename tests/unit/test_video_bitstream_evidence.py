import shutil
import subprocess
import pytest
from app.domain.video_bitstream_evidence import parse_header_evidence,bounded_trace,inspect_video_headers


def line(name,value):return f'[trace_headers @ 0x1234] 3 {name} 000001 = {value}\n'


def test_only_complete_idr_intra_boundaries_are_positive():
    text=line('nal_unit_type',5)+line('slice_type',7)+line('nal_unit_type',1)+line('slice_type',5)
    result=parse_header_evidence(text,'h264')
    assert result['closed_gop']=='REFRESH_BOUNDARIES_VERIFIED'
    assert result['rate_control']=='UNVERIFIED'
    assert parse_header_evidence(text+line('slice_type',7),'h264')['closed_gop']=='UNVERIFIED'
    assert parse_header_evidence('', 'h264')['closed_gop']=='UNVERIFIED'
    assert parse_header_evidence(text,'hevc')['closed_gop']=='UNVERIFIED'
    assert parse_header_evidence(line('nal_unit_type',20)+text,'h264')['closed_gop']=='UNVERIFIED'


def test_hrd_and_varying_packets_do_not_prove_rate_control():
    for flag in [0,1]:
        result=parse_header_evidence(line('cbr_flag[0]',flag),'h264')
        assert result['hrd_cbr_flags']==[flag] and result['rate_control']=='UNVERIFIED'


@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='ffmpeg required')
@pytest.mark.parametrize('opened',[False,True])
def test_real_open_and_closed_gop_are_distinguished_without_false_violation(tmp_path,opened):
    path=tmp_path/'fixture.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x120:rate=25','-t','3','-c:v','libx264','-g','25','-x264-params',f'open-gop={int(opened)}:scenecut=0','-an','-y',str(path)],check=True,timeout=15)
    result=inspect_video_headers(str(path),'h264')
    assert result['status']=='COMPLETE'
    assert result['closed_gop']==('UNVERIFIED' if opened else 'REFRESH_BOUNDARIES_VERIFIED')
    assert result['rate_control']=='UNVERIFIED'
    with pytest.raises(ValueError,match='output limit'):bounded_trace(str(path),max_bytes=1)
    with pytest.raises(ValueError,match='time limit'):bounded_trace(str(path),timeout=0)


def test_missing_probe_and_other_codecs_are_unverified(monkeypatch):
    monkeypatch.setattr('app.domain.video_bitstream_evidence.bounded_trace',lambda *a,**kw:(_ for _ in ()).throw(OSError('missing')))
    assert inspect_video_headers('notread','h264')['status']=='UNVERIFIED'
    assert inspect_video_headers('notread','hevc')['status']=='UNVERIFIED'


def test_unavailable_extra_check_keeps_basic_video_measurements(tmp_path,monkeypatch):
    from app.domain.platform_media_probe import inspect_media,media_findings
    if not shutil.which('ffmpeg'):pytest.skip('ffmpeg required')
    path=tmp_path/'video.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=160x120:r=25','-t','3','-c:v','libx264','-an','-y',str(path)],check=True,timeout=15)
    monkeypatch.setattr('app.domain.video_bitstream_evidence.bounded_trace',lambda *a,**kw:(_ for _ in ()).throw(ValueError('limit')))
    result=inspect_media(path.read_bytes(),'VIDEO','video/mp4')
    assert result['width']==160 and result['header_evidence']['status']=='UNVERIFIED'
    assert any('closed GOP' in text for text in media_findings('instagram','VIDEO',result)[1])
