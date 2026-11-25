"""Local exact-copy constraints, never account readiness or publication authority."""
SOURCES=[
    'https://developers.facebook.com/docs/pages-api/posts/',
    'https://developers.facebook.com/docs/graph-api/reference/page/feed/',
    'https://developers.facebook.com/docs/video-api/guides/reels-publishing/',
]

def blockers(kind,fields):
    reasons=[]
    message=fields.get('description')
    if kind not in {'TEXT','IMAGE','VIDEO'}:
        reasons.append('مسارات Facebook الحالية تقبل نصاً أو صورة منفردة أو Reel، لا هذا النوع.')
    if not isinstance(message,str):
        reasons.append('نص نسخة Facebook غير صالح.')
    elif kind=='VIDEO' and len(message)>2200:
        reasons.append('حد وصف Facebook Reel المحلي المحافظ 2200 حرف. لم يُقص.')
    elif kind in {'TEXT','IMAGE'} and (len(message)>60000 or (kind=='TEXT' and not message.strip())):
        reasons.append('النص مطلوب للنص المنفرد، وحد التجهيز المحلي المحافظ 60000 حرف. لم يُقص.')
    if any(fields.get(k) for k in ['title','tags','alt_text']):
        reasons.append('مسار Facebook الحالي يرسل نص النشر فقط. توجد حقول منفصلة محفوظة للعنوان أو الوسوم أو النص البديل؛ راجعها صراحةً، لن ندمجها أو نتجاهلها عند الإرسال.')
    return reasons
