"""Bounded local inspection, never conversion, upload or publication authority."""
import io
import json
import math
import subprocess
import tempfile
from fractions import Fraction
from PIL import Image
from app.domain.mp4_structure import inspect_mp4_structure
from app.domain.video_bitstream_evidence import inspect_video_headers


def inspect_media(data, kind, mime):
    if kind == 'IMAGE':
        with Image.open(io.BytesIO(data)) as image:
            width,height=image.size
            if width*height>40_000_000: raise ValueError('Image exceeds bounded inspection pixel limit.')
            image.verify()
            return {'format':image.format,'width':width,'height':height,'size_bytes':len(data)}
    if kind != 'VIDEO' or mime not in {'video/mp4','video/quicktime'}:
        raise ValueError('فحص الوسيط هنا يدعم الصور وفيديو MP4/MOV فقط.')
    with tempfile.NamedTemporaryFile() as file:
        file.write(data);file.flush()
        result=subprocess.run(['ffprobe','-f','mov','-protocol_whitelist','file,pipe','-v','error','-show_streams','-show_format','-of','json',file.name],capture_output=True,timeout=15,check=True)
        header_evidence=inspect_video_headers(file.name,next((stream.get('codec_name') for stream in json.loads(result.stdout).get('streams',[]) if stream.get('codec_type')=='video'),None))
    structure=inspect_mp4_structure(data)
    info=json.loads(result.stdout)
    videos=[s for s in info.get('streams',[]) if s.get('codec_type')=='video']
    if len(videos)!=1: raise ValueError('يلزم مسار فيديو واحد قابل للفحص.')
    video=videos[0]
    duration=float(info.get('format',{}).get('duration',video.get('duration',0)))
    fps=float(Fraction(video.get('avg_frame_rate','0')))
    if not math.isfinite(duration) or not math.isfinite(fps) or duration<=0 or fps<=0: raise ValueError('تعذر قياس المدة أو معدل الإطارات.')
    return {**structure,'header_evidence':header_evidence,'format':'MOV/MP4','size_bytes':len(data),'width':int(video.get('width',0)),'height':int(video.get('height',0)),'duration_seconds':duration,'fps':fps,'video_codec':video.get('codec_name'),'pixel_format':video.get('pix_fmt'),'field_order':video.get('field_order'),'video_bitrate':int(video.get('bit_rate') or 0),'audio':[{'codec':s.get('codec_name'),'sample_rate':int(s.get('sample_rate') or 0),'channels':int(s.get('channels') or 0),'bitrate':int(s.get('bit_rate') or 0)} for s in info.get('streams',[]) if s.get('codec_type')=='audio']}


def media_findings(platform,kind,info):
    blockers=[];pending=[]
    width,height=info['width'],info['height']
    if width<=0 or height<=0: return ['تعذر تحديد أبعاد موجبة.'],[]
    if platform=='instagram' and kind=='IMAGE':
        if info['format']!='JPEG': blockers.append('Instagram يتطلب JPEG. لم يُحوّل الأصل.')
        if info['size_bytes']>8_000_000: blockers.append('الصورة تتجاوز8MB. لم تُضغط.')
        if not .8<=width/height<=1.91: blockers.append('نسبة الصورة خارج 4:5 إلى 1.91:1. لم تُقص.')
        pending.append('Instagram قد يغيّر العرض خارج320إلى1440بكسل ويحول اللون إلىsRGB. لم نغير الملف.')
    elif platform=='instagram' and kind=='VIDEO':
        if info['video_codec'] not in {'h264','hevc'}: blockers.append('Reel يتطلب H.264 أوHEVC.')
        if info['pixel_format'] not in {'yuv420p','yuvj420p'}: blockers.append('يلزم تحقق/تحويل اللون إلى4:2:0.')
        if info['field_order'] not in {None,'unknown','progressive'}: blockers.append('Reel يتطلب مسحاً تدريجياً.')
        if not 23<=info['fps']<=60: blockers.append('معدل الإطارات خارج 23 إلى 60 FPS.')
        if not 3<=info['duration_seconds']<=900: blockers.append('مدة Reel خارج 3 ثوان إلى 15 دقيقة.')
        if width>1920 or not .01<=width/height<=10: blockers.append('أبعاد Reel خارج النطاق الموثق.')
        if info['video_bitrate']>25_000_000: blockers.append('تدفق الفيديو يتجاوز25Mbps.')
        if any(s['codec']!='aac' or s['sample_rate']>48000 or s['channels'] not in {1,2} for s in info['audio']): blockers.append('الصوت يتطلب AAC حتى 48kHz وقناة أو قناتين.')
        if not info.get('moov_before_media',False): blockers.append('يلزم موضع moov قبل بيانات الوسيط. الأصل لم يُعد ترتيبه.')
        if info.get('has_edit_lists',True): blockers.append('Reel لا يقبل edit lists. الأصل لم يُعدّل.')
        if any(s.get('bitrate',0)>128_000 for s in info['audio']): blockers.append('معدل الصوت يتجاوز128kbps.')
        if any(not s.get('bitrate') for s in info['audio']): pending.append('لم يصرح الملف بمعدل الصوت لكل المسارات.')
        headers=info.get('header_evidence',{})
        if headers.get('closed_gop')!='REFRESH_BOUNDARIES_VERIFIED':pending.append('closed GOP غير متحقق. ترويسات غير مكتملة أو حدود داخلية دون IDR؛ لا نستنتج أنه مفتوح من ذلك وحده.')
        pending.append('نمط VBR غير متحقق. أعلام HRD أو تغير أحجام الحزم لا تثبت نمط تحكم المشفّر.')
        pending.append('الفحص محدود 50MiB ولا يدعي قبول حد رفع المنصة 300MB.')
        if not info['video_bitrate']: pending.append('لم يصرح الملف بمعدل تدفق الفيديو.')
        if info['field_order'] in {None,'unknown'}: pending.append('نوع المسح لم يصرح به الملف.')
    elif platform=='telegram':
        if kind=='IMAGE':
            if info['size_bytes']>10_000_000: blockers.append('صورة Telegram تتجاوز10MB.')
            if width+height>10000: blockers.append('مجموع عرض وارتفاع صورة Telegram يتجاوز10000بكسل.')
            if max(width/height,height/width)>20: blockers.append('نسبة أبعاد صورة Telegram تتجاوز20.')
        elif kind=='VIDEO' and info['size_bytes']>50_000_000: blockers.append('فيديو Telegram يتجاوز50MB لمسار رفع Bot API.')
        pending.append('قبول Telegram الفعلي وفحص الحمولة والوجهة يبقيان في مسار المعاينة والتنفيذ.')
    else:
        pending.append('هذه قياسات الملف فقط. لم نطبق ملف متطلبات وسيط رسمي لهذه المنصة.')
    pending.append('الحقول والحساب والصلاحيات وقبول المنصة لم تُفحص هنا. لا إذن نشر من هذا الفحص.')
    return blockers,pending
