import struct
import pytest
from app.domain.mp4_structure import inspect_mp4_structure
from app.domain.platform_media_probe import media_findings

def box(kind,payload=b''):return struct.pack('>I4s',8+len(payload),kind)+payload

def test_box_boundaries_real_nested_edit_list_and_fast_start():
    moov=box(b'moov',box(b'trak',box(b'edts',box(b'elst',b'payload'))))
    data=box(b'ftyp')+moov+box(b'mdat',b'elst is not a box here')
    info=inspect_mp4_structure(data)
    assert info['has_edit_lists'] and info['moov_before_media']
    assert not inspect_mp4_structure(box(b'mdat',b'elst')+box(b'moov'))['moov_before_media']
    assert not inspect_mp4_structure(box(b'moov')+box(b'mdat',b'elst'))['has_edit_lists']

@pytest.mark.parametrize('data',[b'',b'abc',struct.pack('>I4s',7,b'moov'),struct.pack('>I4s',999,b'moov'),box(b'moov'),box(b'moov')*2+box(b'mdat')])
def test_malformed_never_passes(data):
    with pytest.raises(ValueError):inspect_mp4_structure(data)

def test_telegram_photo_dimensions_and_file_limits():
    good={'width':640,'height':800,'size_bytes':100,'format':'JPEG'}
    assert not media_findings('telegram','IMAGE',good)[0]
    assert len(media_findings('telegram','IMAGE',{**good,'width':10001,'height':100,'size_bytes':10_000_001})[0])==3

def test_instagram_structure_audio_limits_stay_separate_from_unverified_gop():
    info={'width':1080,'height':1920,'size_bytes':100,'video_codec':'h264','pixel_format':'yuv420p','field_order':'progressive','duration_seconds':30,'fps':30,'video_bitrate':2_000_000,'audio':[{'codec':'aac','sample_rate':48000,'channels':2,'bitrate':129000}],'moov_before_media':False,'has_edit_lists':True}
    blockers,pending=media_findings('instagram','VIDEO',info)
    assert len(blockers)==3
    assert any('GOP' in p for p in pending)
