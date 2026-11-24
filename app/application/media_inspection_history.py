"""Private historical evidence. Never a cache of platform acceptance."""
from uuid import UUID
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,PlatformMediaInspectionModel
from app.application.distribution_readiness import source_fingerprint
from app.application.platform_media_probe import probe_platform_media
PROBE_VERSION='2026-11-24.1'


def describe(row,copy,record):
    reasons=[]
    if record.source_fingerprint!=source_fingerprint(row):reasons.append('تغير الأصل.')
    if record.copy_version!=copy.version:reasons.append('تغير إصدار نسخة المنصة.')
    current_media=copy.selected_media_id if record.selected else None
    if record.media_id!=current_media:reasons.append('تغير اختيار وسيط النسخة.')
    if record.probe_version!=PROBE_VERSION:reasons.append('تغير إصدار الفحص.')
    if row.review_status!='APPROVED' or row.status!='AVAILABLE':reasons.append('الأصل غير معتمد ومتاح حالياً.')
    return {'id':str(record.id),'created_at':record.created_at.isoformat(),'selected':record.selected,
        'media_id':str(record.media_id) if record.media_id else None,'sha256':record.sha256,
        'copy_version':record.copy_version,'probe_version':record.probe_version,'stale':bool(reasons),
        'stale_reasons':reasons,'result':record.result,'execution_authorized':False,
        'caveat':'سجل قياسات سابق مرتبط بإصدار، لا يعيد قراءة الملف ولا يثبت قبوله أو عدم تغير بايتاته حالياً. أعد الفحص قبل التنفيذ.'}


async def list_inspections(session,uid,platform):
    row=await session.get(ArtifactModel,uid);copy=await session.get(PlatformCopyModel,(uid,platform))
    if row is None or copy is None:raise ValueError('جهّز نسخة المنصة أولاً.')
    records=(await session.execute(select(PlatformMediaInspectionModel).where(PlatformMediaInspectionModel.artifact_id==uid,PlatformMediaInspectionModel.platform==platform).order_by(PlatformMediaInspectionModel.created_at.desc(),PlatformMediaInspectionModel.id.desc()).limit(20))).scalars().all()
    return {'items':[describe(row,copy,r) for r in records],'execution_authorized':False,'limit':20}


async def record_inspection(session,uid,platform,*,fingerprint,version,selected):
    # Validate the operator's displayed context before starting a potentially long read.
    row=await session.get(ArtifactModel,uid);copy=await session.get(PlatformCopyModel,(uid,platform))
    if row is None or copy is None or source_fingerprint(row)!=fingerprint or copy.version!=version:
        raise ValueError('تغير الأصل أو النسخة. أعد تحميلها قبل حفظ الفحص.')
    result=await probe_platform_media(session,uid,platform,selected=selected)
    # Refresh under the same lock order as media selection. No lock across network I/O.
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    copy=(await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==uid,PlatformCopyModel.platform==platform).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None or copy is None or source_fingerprint(row)!=fingerprint or copy.version!=version or copy.source_fingerprint!=fingerprint or row.review_status!='APPROVED' or row.status!='AVAILABLE':
        raise ValueError('تغير الأصل أو النسخة أثناء الفحص؛ لم يُحفظ سجل قديم كأنه حالي.')
    media_id=UUID(result['inspected_media_id']) if result.get('inspected_media_id') else None
    if selected and copy.selected_media_id!=media_id:raise ValueError('تغير وسيط النسخة أثناء الفحص.')
    if result.get('source_fingerprint')!=fingerprint or result.get('copy_version')!=version:raise ValueError('نتيجة الفحص لا تطابق الإصدار المطلوب.')
    record=PlatformMediaInspectionModel(artifact_id=uid,platform=platform,source_fingerprint=fingerprint,copy_version=version,media_id=media_id,selected=selected,sha256=result['sha256'],probe_version=PROBE_VERSION,result=result)
    session.add(record);await session.commit()
    return describe(row,copy,record)
