"""Bounded header evidence, never infer encoder rate control from packet variance."""
import os
import re
import selectors
import subprocess
import time


def bounded_trace(path, *, timeout=15, max_bytes=8*1024*1024):
    command=['ffmpeg','-hide_banner','-nostdin','-f','mov','-protocol_whitelist','file,pipe','-i',path,'-map','0:v:0','-c','copy','-bsf:v','trace_headers','-f','null','-']
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    content=bytearray();deadline=time.monotonic()+timeout
    try:
        with selectors.DefaultSelector() as poll:
            poll.register(process.stdout,selectors.EVENT_READ)
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise ValueError('header inspection time limit')
                events=poll.select(min(remaining,.5))
                if not events:continue
                block=os.read(process.stdout.fileno(),65536)
                if not block:break
                content.extend(block)
                if len(content)>max_bytes:raise ValueError('header inspection output limit')
        if process.wait(timeout=max(.1,deadline-time.monotonic())):raise ValueError('header inspection unavailable or invalid')
        return content.decode('utf-8',errors='replace')
    finally:
        if process.poll() is None:process.kill()
        process.wait();process.stdout.close()


def parse_header_evidence(text,codec):
    nal=None;first=None;intra=0;refresh=0;nonrefresh=0;unsupported=False;cbr=[];slices=0
    for line in text.splitlines():
        match=re.search(r'\bnal_unit_type\s+[01]+\s+=\s+(\d+)\s*$',line)
        if match:
            nal=int(match[1])
            if codec=='h264' and nal in {2,3,4,14,20,21}:unsupported=True
        match=re.search(r'\bcbr_flag(?:\[\d+\])?\s+[01]+\s+=\s+([01])\s*$',line)
        if match:cbr.append(int(match[1]))
        match=re.search(r'\bslice_type\s+[01]+\s+=\s+(\d+)\s*$',line)
        if not match:continue
        slices+=1
        if first is None:first=nal
        value=int(match[1]);is_intra=value%5 in {2,4} if codec=='h264' else value==2
        if is_intra:
            intra+=1
            if (codec=='h264' and nal==5) or (codec=='hevc' and nal in {16,17,18,19,20}):refresh+=1
            else:nonrefresh+=1
    # IDR/BLA refresh clears cross-boundary references. Non-IDR I/CRA may or may
    # not form an open GOP; it cannot prove a violation without reference analysis.
    starts_refresh=(first==5 if codec=='h264' else first in {16,17,18,19,20})
    proven=codec=='h264' and slices>0 and intra>0 and nonrefresh==0 and starts_refresh and not unsupported
    return {'status':'COMPLETE','closed_gop':'REFRESH_BOUNDARIES_VERIFIED' if proven else 'UNVERIFIED',
        'slice_headers':slices,'intra_slice_headers':intra,'refresh_intra_slice_headers':refresh,'nonrefresh_intra_slice_headers':nonrefresh,
        'hrd_cbr_flags':sorted(set(cbr)),'rate_control':'UNVERIFIED',
        'method':'Complete bounded trace_headers; IDR/BLA intra boundaries only. No inference from keyframe flags, packet-size variation or absent HRD.'}


def inspect_video_headers(path,codec):
    if codec!='h264':return {'status':'UNVERIFIED','closed_gop':'UNVERIFIED','rate_control':'UNVERIFIED','reason':'تحليل حدود GOP متاح لـH.264 فقط، لا نفترض نتيجةHEVC.'}
    try:return parse_header_evidence(bounded_trace(path),codec)
    except (OSError,ValueError,subprocess.SubprocessError):
        return {'status':'UNVERIFIED','closed_gop':'UNVERIFIED','rate_control':'UNVERIFIED','reason':'فحص ترويسات الفيديو غير متاح أو تجاوز حد15ثانية/8MiB. لم يُغيّر الملف.'}
