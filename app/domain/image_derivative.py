"""Explicit private JPEG preview. No crop, AI, storage writes or original edits."""
import io
import re
import warnings
from PIL import Image, ImageCms, ImageOps, features

def jpeg_preview(data,background):
    if not features.check('littlecms2'):
        raise ValueError('تحويل JPEG غير متاح مؤقتاً: دعم إدارة الألوان غير مثبت. بقية الموقع والجدولة لا تتأثر.')
    if not isinstance(background,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',background):
        raise ValueError('اختر لون خلفية بصيغة #RRGGBB للشفافية المحتملة.')
    if len(data)>50*1024*1024:raise ValueError('الصورة تتجاوز حد القراءة الآمن.')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as source:
            if source.width*source.height>40_000_000:raise ValueError('الصورة تتجاوز40مليون بكسل.')
            if getattr(source,'n_frames',1)!=1:raise ValueError('لا نحول صورة متحركة أو متعددة الصفحات إلى لقطة واحدة.')
            source.load()
            image=ImageOps.exif_transpose(source)
            width,height=image.size
            if not .8<=width/height<=1.91:raise ValueError('النسبة خارج4:5إلى1.91:1. يلزم قرار قص منفصل؛ لم نقص الصورة.')
            alpha=image.convert('RGBA').getchannel('A')
            profile=image.info.get('icc_profile')
            rgb=image.convert('RGB')
            if profile:
                rgb=ImageCms.profileToProfile(image.convert('CMYK') if image.mode=='CMYK' else rgb,ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGB')
            elif image.mode=='CMYK':raise ValueError('صورة CMYK بلا ملف لون موثوق؛ لم نخمن التحويل.')
            composite=Image.new('RGB',image.size,background)
            composite.paste(rgb,mask=alpha)
            target=max(320,min(1440,width))
            if target!=width:composite=composite.resize((target,round(height*target/width)),Image.Resampling.LANCZOS)
            out=io.BytesIO()
            composite.save(out,format='JPEG',quality=90,optimize=True,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
            content=out.getvalue()
            if len(content)>8_000_000:raise ValueError('النسخة تتجاوز8MB بجودة90. لم نخفض الجودة تلقائياً.')
            return content,{'width':composite.width,'height':composite.height,'format':'JPEG','size_bytes':len(content),'quality':90,'background':background,'color_space':'sRGB','assumed_srgb_without_profile':not bool(profile),'orientation_applied':True,'metadata_removed':True,'cropped':False}
