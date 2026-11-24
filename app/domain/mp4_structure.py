"""Bounded ISO BMFF box structure checks, without decoding or rewriting bytes."""
import struct

CONTAINERS={b'moov',b'trak',b'mdia',b'minf',b'stbl',b'edts',b'mvex',b'moof',b'traf'}

def inspect_mp4_structure(data):
    count=0
    top=[]
    has_edit_list=False
    def walk(start,end,depth=0):
        nonlocal count,has_edit_list
        if depth>12:raise ValueError('MP4 nesting exceeds inspection limit.')
        offset=start
        while offset<end:
            count+=1
            if count>10000 or end-offset<8:raise ValueError('Invalid or excessive MP4 boxes.')
            size,kind=struct.unpack_from('>I4s',data,offset);header=8
            if size==1:
                if end-offset<16:raise ValueError('Truncated MP4 extended size.')
                size=struct.unpack_from('>Q',data,offset+8)[0];header=16
            elif size==0:size=end-offset
            if size<header or offset+size>end:raise ValueError('Invalid MP4 box boundary.')
            if depth==0:top.append((kind,offset))
            if kind==b'elst':has_edit_list=True
            if kind in CONTAINERS:walk(offset+header,offset+size,depth+1)
            offset+=size
    walk(0,len(data))
    moov=[pos for kind,pos in top if kind==b'moov']
    mdat=[pos for kind,pos in top if kind==b'mdat']
    if len(moov)!=1 or not mdat:raise ValueError('MP4 requires one moov and media data.')
    return {'moov_before_media':moov[0]<min(mdat),'has_edit_lists':has_edit_list,
            'fragmented':any(kind==b'moof' for kind,_ in top),'box_count':count}
