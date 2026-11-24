import io
import pytest
from PIL import Image
from app.domain.image_derivative import jpeg_preview

def png(mode='RGBA',size=(640,800),color=(255,0,0,0),**kw):
    out=io.BytesIO();Image.new(mode,size,color).save(out,format='PNG',**kw);return out.getvalue()

def test_transparency_explicit_background_color_size_and_no_original_mutation():
    data=png();before=bytes(data)
    white,info=jpeg_preview(data,'#ffffff');black,_=jpeg_preview(data,'#000000')
    assert data==before and info['cropped'] is False and info['color_space']=='sRGB'
    with Image.open(io.BytesIO(white)) as image:
        assert image.format=='JPEG' and image.size==(640,800) and image.getpixel((0,0))[0]>250
        assert image.info['icc_profile'] and not image.getexif()
    with Image.open(io.BytesIO(black)) as image:assert image.getpixel((0,0))[0]<5

@pytest.mark.parametrize('size,expected',[((100,100),(320,320)),((2000,2000),(1440,1440))])
def test_width_normalized_without_cropping(size,expected):
    data,_=jpeg_preview(png(size=size),'#ffffff')
    with Image.open(io.BytesIO(data)) as image:assert image.size==expected

@pytest.mark.parametrize('data,bg',[(png(size=(100,1000)),'#ffffff'),(b'bad','#ffffff'),(png(),'invalid'),(png(icc_profile=b'bad'),'#ffffff')])
def test_unsafe_or_editorial_decisions_refused(data,bg):
    with pytest.raises(Exception):jpeg_preview(data,bg)

def test_animation_never_silently_flattened():
    out=io.BytesIO();Image.new('RGB',(400,400),'red').save(out,format='PNG',save_all=True,append_images=[Image.new('RGB',(400,400),'blue')],duration=100)
    with pytest.raises(ValueError):jpeg_preview(out.getvalue(),'#ffffff')

def test_exif_orientation_applied_and_sensitive_metadata_stripped():
    exif=Image.Exif();exif[274]=6;exif[270]='private description'
    out=io.BytesIO();Image.new('RGB',(800,640),'red').save(out,format='JPEG',exif=exif)
    data,info=jpeg_preview(out.getvalue(),'#ffffff')
    assert (info['width'],info['height'])==(640,800)
    with Image.open(io.BytesIO(data)) as image:assert not image.getexif()


def test_preview_hash_is_stable_across_profile_creation_times(monkeypatch):
    import time
    from PIL import ImageCms
    original=ImageCms.ImageCmsProfile.tobytes
    calls=0
    def timestamped(self):
        nonlocal calls
        calls+=1
        result=bytearray(original(self));result[24:36]=bytes([0,0,0,0,0,0,0,0,0,0,0,calls])
        return bytes(result)
    monkeypatch.setattr(ImageCms.ImageCmsProfile,'tobytes',timestamped)
    assert jpeg_preview(png(),'#ffffff')[0]==jpeg_preview(png(),'#ffffff')[0]
