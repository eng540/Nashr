"""Bounded format-only private video derivative. Never trims, crops or generates."""
import subprocess
import threading
import tempfile
from pathlib import Path
from app.domain.platform_media_probe import inspect_video_file,media_findings


_conversion_slot=threading.BoundedSemaphore(1)

def video_derivative(data: bytes, platform: str):
    if not _conversion_slot.acquire(blocking=False):raise ValueError('تحويل فيديو آخر جارٍ. حاول لاحقاً؛ لم يُغيّر الأصل.')
    try:return _convert(data,platform)
    finally:_conversion_slot.release()


def _convert(data: bytes, platform: str):
    if platform not in {'instagram','facebook'}:raise ValueError('نسخ الفيديو الخاصة لـInstagram وFacebook فقط.')
    if not 0<len(data)<=50_000_000:raise ValueError('حد التحويل المحلي50MB.')
    with tempfile.TemporaryDirectory() as td:
        src=Path(td)/'source.mp4';out=Path(td)/'derivative.mp4';src.write_bytes(data)
        original=inspect_video_file(str(src))
        import json
        raw=json.loads(subprocess.run(['ffprobe','-f','mov','-protocol_whitelist','file,pipe','-v','error','-show_streams','-of','json',str(src)],capture_output=True,timeout=15,check=True).stdout)
        streams=raw.get('streams',[])
        if len(streams)!=2 or any(x.get('codec_type') not in {'video','audio'} for x in streams):raise ValueError('يلزم مسار فيديو واحد وصوت واحد فقط، لا إسقاط لمسارات إضافية.')
        video=next(x for x in streams if x['codec_type']=='video')
        if video.get('avg_frame_rate')!=video.get('r_frame_rate'):raise ValueError('توقيت متغير أو غير محسوم؛ لا تحويل صامت للإطارات.')
        if video.get('sample_aspect_ratio') not in {None,'1:1','0:1'} or any(x.get('rotation',0)!=0 for x in video.get('side_data_list',[])):raise ValueError('يلزم فيديو ببكسل مربع ودون تدوير مسجل؛ لا تغيير صامت للأبعاد.')
        if not 3<=original['duration_seconds']<=90:raise ValueError('التحويل يدعم3إلى90ثانية دون قص.')
        if not 24<=original['fps']<=60:raise ValueError('معدل الإطارات خارج24إلى60؛ لا تغيير صامت للتوقيت.')
        if original['width']*original['height']>16_000_000:raise ValueError('أبعاد الأصل تتجاوز حد التحويل المحلي.')
        if original['video_codec'] not in {'h264','hevc'} or original['pixel_format'] not in {'yuv420p','yuvj420p'} or original['field_order'] not in {None,'unknown','progressive'}:raise ValueError('التحويل المحدود يدعمH.264/HEVCتدريجياً4:2:0فقط.')
        if len(original['audio'])!=1:raise ValueError('يلزم مسار صوت واحد؛ لا إسقاط أو اختراع صوت.')
        bitrate='120k' if platform=='instagram' else '160k'
        args=['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(src),'-map','0:v:0','-map','0:a:0','-map_metadata','-1','-vf','scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1','-threads','2','-c:v','libx264','-preset','fast','-crf','20','-maxrate','20M','-bufsize','40M','-pix_fmt','yuv420p','-g','60','-keyint_min','60','-sc_threshold','0','-bf','0','-flags','+cgop','-c:a','aac','-ac','2','-ar','48000','-b:a',bitrate,'-fs','49000000','-movflags','+faststart','-use_editlist','0','-avoid_negative_ts','disabled',str(out)]
        subprocess.run(args,check=True,capture_output=True,timeout=180)
        measured=inspect_video_file(str(out))
        if measured['size_bytes']>=49_000_000:raise ValueError('تجاوزت النسخة حد الحجم الآمن؛ لم تُقبل.')
        if abs(measured['duration_seconds']-original['duration_seconds'])>.25:raise ValueError('اختلفت مدة النسخة؛ لم تُقبل.')
        if measured['width']!=1080 or measured['height']!=1920 or measured['header_evidence'].get('closed_gop')!='REFRESH_BOUNDARIES_VERIFIED':raise ValueError('تعذر إثبات أبعاد النسخة أو حدودGOP.')
        if platform=='instagram' and media_findings(platform,'VIDEO',measured)[0]:raise ValueError('لم تجتز النسخة قياساتInstagram المحلية.')
        if platform=='facebook' and any(a['bitrate']<128000 for a in measured['audio']):raise ValueError('لم تجتز النسخة قياس صوتFacebook المحلي.')
        return out.read_bytes(),measured
