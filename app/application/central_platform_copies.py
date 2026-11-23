"""Linked preparation records, never publication authority or media conversion."""
from datetime import datetime, timezone
import re
from sqlalchemy import select
from app.application.distribution_readiness import PLATFORMS, source_fingerprint
from app.domain.telegram_copy import telegram_publish_text
from app.application.telegram_copy_readiness import telegram_copy_blockers
from app.infrastructure.database.models import ArtifactModel, PlatformCopyModel

SOURCES = {
 'telegram':['https://core.telegram.org/bots/api'],
 'youtube':['https://developers.google.com/youtube/data/reference/rest/v3/videos','https://developers.google.com/youtube/data/reference/rest/v3/videos/insert'],
 'instagram':['https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/','https://developers.facebook.com/documentation/instagram-platform/content-publishing'],
}
FIELDS = {'title','description','tags','alt_text'}


def defaults(row, platform):
    meta=row.artifact_metadata or {}
    text=telegram_publish_text(row) if platform=='telegram' else (row.content if row.content is not None else str(meta.get('caption') or ''))
    # Title is an existing title only, never a shortened description or invented hook.
    return {'title':str(meta.get('title') or ''),'description':text,'tags':[],'alt_text':''}


def evaluate(row, copy):
    fields=copy.fields
    blockers=[]
    warnings=[]
    stale=copy.source_fingerprint != source_fingerprint(row)
    if row.review_status!='APPROVED' or row.status!='AVAILABLE':
        blockers.append('المادة الأصلية غير معتمدة ومتاحة.')
    if stale:
        blockers.append('تغير الأصل منذ تجهيز هذه النسخة. لم نستبدل تعديلاتك؛ راجعها واربطها بالإصدار الحالي صراحةً.')
    title,description,tags,alt=fields['title'],fields['description'],fields['tags'],fields['alt_text']
    media=[]
    if copy.platform=='telegram':
        from types import SimpleNamespace
        candidate=SimpleNamespace(kind=row.kind,content=description,artifact_metadata=row.artifact_metadata,mime_type=row.mime_type,storage_uri=row.storage_uri)
        blockers.extend(telegram_copy_blockers(candidate))
        if row.kind in {'STICKER','VIDEO_NOTE'} and description:
            blockers.append('هذا النوع لا ينشر تعليقاً في Telegram. اترك نص النشر فارغاً.')
        if row.kind=='QUIZ' and description != row.content:
            blockers.append('سؤال الاختبار مرتبط بحمولته المعتمدة. لا تعدله من نسخة نصية.')
        if (row.artifact_metadata or {}).get('telegram_native') is not None and description != telegram_publish_text(row):
            blockers.append('هذه حمولة Telegram مركبة؛ النص وحده لا يغير حقولها المعتمدة.')
        media.append('فحص الوسائط والحمولات المركبة النهائي لم ينفذ هنا.')
    elif copy.platform=='youtube':
        if row.kind!='VIDEO': blockers.append('مسار YouTube الموثق هنا للفيديو فقط.')
        if not title.strip() or len(title)>100 or '<' in title or '>' in title:
            blockers.append('العنوان مطلوب، بحد100حرف ودون علامتي < و >.')
        if len(description.encode('utf-8'))>5000 or '<' in description or '>' in description:
            blockers.append('الوصف يتجاوز5000بايتUTF-8 أو يحتوي < أو >. لم يُقص.')
        units=sum(len(tag)+(2 if ' ' in tag else 0) for tag in tags)+max(0,len(tags)-1)
        if units>500 or any(not tag.strip() for tag in tags): blockers.append('الكلمات المفتاحية تتجاوز500حرف مع الفواصل وعلامات الاقتباس للعبارات.')
        media.append('ملف الفيديو والرفع ومقاس الغلاف لم تُفحص. التصنيف وإعدادات الجمهور والخصوصية تحتاج اختياراً عند ربط القناة.')
    elif copy.platform=='instagram':
        if row.kind not in {'IMAGE','VIDEO'}: blockers.append('هذا المسار يجهز صورة منفردة أوReel فقط.')
        if len(description)>2200 or len(re.findall(r'(?<!\w)#\w+',description))>30 or len(re.findall(r'(?<!\w)@\w+',description))>20:
            blockers.append('التعليق يتجاوز2200حرف أو30وسماً أو20إشارة. لم يُقص.')
        if len(alt)>1000: blockers.append('النص البديل يتجاوز1000حرف.')
        if row.kind!='IMAGE' and alt: blockers.append('النص البديل موثق للصور فقط، لاReels.')
        if row.kind=='IMAGE' and row.mime_type!='image/jpeg': blockers.append('الصورة تتطلبJPEG للنشر الرسمي. الأصل لم يُحوّل.')
        media.append('يلزم فحص أبعاد/حجم الصورة أو ترميز/مدة الفيديو. لم ننشئ رابط وسيط متاحاً للمنصة.')
        if title: warnings.append('Instagram لا يستخدم عنواناً منفصلاً هنا. المحفوظ للتنظيم فقط، لن يضاف للتعليق تلقائياً.')
    else:
        blockers.append('لم يكتمل ملف المتطلبات الرسمي لهذه المنصة. الحقول محفوظة للتحرير فقط.')
    if copy.platform!='youtube' and tags:
        warnings.append('الكلمات المفتاحية لا تُلصق بالنص تلقائياً. ضع الوسوم داخل نص النشر إذا أردتها ضمنه.')
    return {'platform':copy.platform,'label':PLATFORMS[copy.platform],'fields':fields,'version':copy.version,
            'source_fingerprint':copy.source_fingerprint,'current_source_fingerprint':source_fingerprint(row),
            'origin':copy.origin,'source_stale':stale,'central_approval':row.review_status,
            'field_status':'BLOCKED' if blockers else 'FIELDS_VALIDATED','blockers':blockers,'warnings':warnings,
            'media_checks_pending':media,'execution_status':'NOT_AUTHORIZED',
            'execution_blockers':['هذه نسخة تجهيز فقط. لا موصل نشر أو حساب أو موعد أو إذن تنفيذ من هذا الحفظ.'],
            'sources':SOURCES.get(copy.platform,[]),'checked_on':'2026-11-24',
            'updated_at':copy.updated_at.isoformat() if copy.updated_at else None}


async def prepare_copies(session,row):
    if row.kind=='POST' or (row.artifact_metadata or {}).get('source_type')=='PLATFORM_VARIANT':
        raise ValueError('اختر المادة الأصلية من مسار المخرجات.')
    existing={item.platform:item for item in (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==row.id))).scalars().all()}
    for platform in PLATFORMS:
        if platform not in existing:
            copy=PlatformCopyModel(artifact_id=row.id,platform=platform,source_fingerprint=source_fingerprint(row),fields=defaults(row,platform),origin='UNCHANGED_ORIGINAL',version=1)
            session.add(copy)
            existing[platform]=copy
    await session.flush()
    return [evaluate(row,existing[platform]) for platform in PLATFORMS]


async def get_copies(session,uid):
    row=await session.get(ArtifactModel,uid)
    if row is None or row.kind=='POST': raise ValueError('المادة الأصلية غير موجودة.')
    copies=(await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==uid).order_by(PlatformCopyModel.platform))).scalars().all()
    return {'artifact_id':str(uid),'items':[evaluate(row,copy) for copy in copies]}


async def update_copy(session,uid,platform,fields,version,current_fingerprint):
    if set(fields)!=FIELDS or any(not isinstance(fields[k],str) for k in FIELDS-{'tags'}) or not isinstance(fields['tags'],list) or any(not isinstance(tag,str) for tag in fields['tags']):
        raise ValueError('حقول النسخة غير صالحة.')
    if any(len(fields[k])>50000 for k in FIELDS-{'tags'}) or len(fields['tags'])>100 or any(len(tag)>500 for tag in fields['tags']):
        raise ValueError('حقول النسخة أكبر من حد التخزين الآمن.')
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())).scalar_one_or_none()
    copy=await session.get(PlatformCopyModel,(uid,platform))
    if row is None or copy is None: raise ValueError('جهّز النسخة أولاً.')
    if version!=copy.version: raise ValueError('حُدثت النسخة في نافذة أخرى. أعد تحميلها قبل الحفظ.')
    if source_fingerprint(row)!=current_fingerprint: raise ValueError('تغير الأصل منذ فتح المحرر. أعد تحميل المعاينة.')
    copy.fields=fields
    copy.source_fingerprint=current_fingerprint
    copy.origin='USER_EDITED'
    copy.version+=1
    copy.updated_at=datetime.now(timezone.utc)
    await session.commit()
    return evaluate(row,copy)
