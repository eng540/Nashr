"""Private Page preparation. No network, storage, jobs, or publishing consent."""
import re
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,FacebookReviewDraftModel,PlatformMediaInspectionModel
from app.application.distribution_readiness import source_fingerprint
from app.application.instagram_plan_review import fingerprint
from app.application.media_inspection_history import describe


def choices(page_id=None,public_page_acknowledged=None,rights_confirmed=None):
    if page_id is not None and (not isinstance(page_id,str) or not re.fullmatch('[0-9]{1,100}',page_id)):
        raise ValueError('معرف صفحة Facebook غير صالح. لا يثبت إدخاله ملكية الصفحة أو ربطها.')
    if any(x is not None and type(x) is not bool for x in [public_page_acknowledged,rights_confirmed]):
        raise ValueError('يلزم اختيار الجمهور والحقوق صراحةً.')
    return dict(page_id=page_id,public_page_acknowledged=public_page_acknowledged,rights_confirmed=rights_confirmed)


async def preview(session,uid,**values):
    intent=choices(**values)
    row=await session.get(ArtifactModel,uid,populate_existing=True)
    copy=await session.get(PlatformCopyModel,(uid,'facebook'),populate_existing=True)
    if row is None or copy is None or row.kind not in {'TEXT','IMAGE'}:
        raise ValueError('اختر أصلاً نصياً أو صورة ونسخة Facebook محفوظة أولاً.')
    stale=copy.source_fingerprint != source_fingerprint(row)
    blockers=['الصفحة المقترحة غير مربوطة، ولم تُتحقق صلاحيات النشر أو مهام الحساب عليها.','لم يُختبر قبول Meta الفعلي. هذه مسودة مراجعة لا خطة تشغيل.']
    if row.review_status != 'APPROVED' or row.status != 'AVAILABLE':blockers.append('الأصل غير معتمد ومتاح حالياً.')
    if stale:blockers.append('تغير الأصل بعد حفظ نسخة Facebook. راجعها واحفظها مجدداً.')
    if not intent['page_id']:blockers.append('يلزم معرف الصفحة المقترحة، لا رمز وصول.')
    if intent['public_page_acknowledged'] is not True:blockers.append('يلزم تأكيد أن منشور الصفحة المقترح موجّه للجمهور، وليس منشوراً خاصاً.')
    if intent['rights_confirmed'] is not True:blockers.append('يلزم إقرار امتلاك حقوق النص والصورة أو إذن استخدامهما.')
    message=copy.fields.get('description','')
    if not isinstance(message,str):raise ValueError('نص النسخة غير صالح.')
    if (row.kind == 'TEXT' and not message.strip()) or len(message)>60000:blockers.append('النص فارغ أو يتجاوز حد التجهيز المحلي 60000 حرف. لم يُقص.')
    if any(copy.fields.get(k) for k in ['title','tags','alt_text']):blockers.append('المسار الحالي يدعم نص المنشور فقط. العنوان والوسوم المنفصلة والنص البديل تحتاج دعماً صريحاً، لن نتجاهلها عند النشر.')
    inspection=None
    if row.kind == 'IMAGE':
        if row.mime_type not in {'image/jpeg','image/png'} or copy.selected_media_id is not None:blockers.append('المسار الجاري تطويره يدعم أصل JPEG أو PNG فقط، دون تبديل وسيط.')
        records=(await session.execute(select(PlatformMediaInspectionModel).where(PlatformMediaInspectionModel.artifact_id==uid,PlatformMediaInspectionModel.platform=='facebook').order_by(PlatformMediaInspectionModel.created_at.desc(),PlatformMediaInspectionModel.id.desc()).limit(20))).scalars().all()
        for record in records:
            if record.selected and not describe(row,copy,record)['stale']:
                inspection=dict(id=str(record.id),sha256=record.sha256,measurements=record.result.get('measurements',{}))
                blockers.extend(record.result.get('blockers',[]));break
        if not inspection:blockers.append('لا يوجد فحص محفوظ حديث للصورة المحددة. المعاينة لا تقرأ الملف.')
        elif inspection['measurements'].get('size_bytes',4_000_001)>4_000_000:blockers.append('حد الصور المحلي المحافظ 4000000 بايت. لم تُصغّر الصورة.')
    payload=dict(artifact_id=str(uid),kind=row.kind,source_fingerprint=source_fingerprint(row),copy_version=copy.version,fields=copy.fields,intent=intent,inspection=inspection,blockers=list(dict.fromkeys(blockers)),page_verified=False,execution_enabled=False,job_created=False,outgoing_approval_recorded=False)
    return {**payload,'preview_hash':fingerprint(payload),'can_save_draft':bool(intent['page_id'] and intent['public_page_acknowledged'] is True and intent['rights_confirmed'] is True and row.review_status=='APPROVED' and row.status=='AVAILABLE' and not stale),'caveat':'حفظ خاص فقط. لا نشر أو موعد أو ربط حساب أو إتاحة صورة على الإنترنت. إدخال صفحة وإقرارات تجهيز لا يسجل موافقة إرسال.'}


async def save_draft(session,uid,*,preview_hash,**values):
    await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())
    await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==uid,PlatformCopyModel.platform=='facebook').with_for_update())
    current=await preview(session,uid,**values)
    if current['preview_hash']!=preview_hash:raise ValueError('تغير الأصل أو النسخة أو الفحص أو خيارات المراجعة. اعرض المعاينة مجدداً.')
    if not current['can_save_draft']:raise ValueError('أكمل الصفحة المقترحة وإقرارات التجهيز واعتماد الأصل قبل حفظ المسودة.')
    record=(await session.execute(select(FacebookReviewDraftModel).where(FacebookReviewDraftModel.artifact_id==uid,FacebookReviewDraftModel.snapshot_hash==preview_hash,FacebookReviewDraftModel.state=='DRAFT'))).scalars().first()
    if not record:
        record=FacebookReviewDraftModel(artifact_id=uid,snapshot_hash=preview_hash,snapshot=current,state='DRAFT');session.add(record);await session.commit()
    return await describe_draft(session,record)


async def describe_draft(session,record):
    try:
        current=await preview(session,record.artifact_id,**record.snapshot['intent']);stale=current['preview_hash']!=record.snapshot_hash
    except ValueError:stale=True
    return dict(id=str(record.id),state=record.state,created_at=record.created_at.isoformat(),snapshot=record.snapshot,stale=stale,execution_enabled=False)


async def list_drafts(session,uid):
    records=(await session.execute(select(FacebookReviewDraftModel).where(FacebookReviewDraftModel.artifact_id==uid).order_by(FacebookReviewDraftModel.created_at.desc()).limit(20))).scalars().all()
    return {'items':[await describe_draft(session,r) for r in records],'execution_enabled':False}


async def cancel_draft(session,uid,draft_id):
    record=(await session.execute(select(FacebookReviewDraftModel).where(FacebookReviewDraftModel.id==draft_id,FacebookReviewDraftModel.artifact_id==uid).with_for_update())).scalar_one_or_none()
    if record is None or record.state not in {'DRAFT','CANCELLED'}:raise ValueError('مسودة مراجعة غير موجودة أو لا يمكن إلغاؤها محلياً.')
    record.state='CANCELLED';await session.commit()
    return dict(id=str(record.id),state=record.state,remote_changed=False,execution_enabled=False)
