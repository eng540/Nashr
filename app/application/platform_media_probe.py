"""Read-only, explicit inspection of private original bytes."""
import asyncio
import hashlib
from datetime import datetime,timezone
from app.application.distribution_readiness import source_fingerprint
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,PlatformCopyMediaModel
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.domain.platform_media_probe import inspect_media,inspect_video_file,media_findings


async def probe_platform_media(session,uid,platform,selected=False):
    row=await session.get(ArtifactModel,uid)
    if row is None or row.status!='AVAILABLE' or row.review_status!='APPROVED' or row.kind not in {'IMAGE','VIDEO'} or not row.storage_uri:
        raise ValueError('اختر صورة أو فيديو أصلياً معتمداً ومتاحاً.')
    copy=await session.get(PlatformCopyModel,(uid,platform))
    if copy is None: raise ValueError('جهّز نسخة المنصة أولاً.')
    fingerprint=source_fingerprint(row)
    version=copy.version
    if copy.source_fingerprint!=fingerprint: raise ValueError('تغير الأصل منذ تجهيز النسخة. راجعها أولاً.')
    uri=row.storage_uri
    mime=row.mime_type
    media_id=None
    expected_hash=None
    if selected and copy.selected_media_id:
        asset=await session.get(PlatformCopyMediaModel,copy.selected_media_id)
        if asset is None or asset.artifact_id!=uid or asset.platform!=platform or asset.source_fingerprint!=fingerprint:
            raise ValueError('الوسيط المختار قديم أو لا يتبع النسخة. أعد تجهيزه.')
        uri=asset.storage_uri;mime=asset.mime_type;media_id=str(asset.id);expected_hash=asset.sha256
    try:
        storage=S3ArtifactStorage.from_environment()
        if row.kind=='VIDEO':
            if mime not in {'video/mp4','video/quicktime'}:raise ValueError('فحص الفيديو يدعم MP4/MOV فقط.')
            info,digest=await storage.inspect_local_file(uri,inspect_video_file,max_bytes=300_000_000)
        else:
            data=await storage.get_bytes(uri,max_bytes=50*1024*1024)
            digest=hashlib.sha256(data).hexdigest()
            info=await asyncio.to_thread(inspect_media,data,row.kind,mime)
        if expected_hash and digest!=expected_hash:
            raise ValueError('بايتات الوسيط المحفوظ اختلفت عن هاشه المسجل. لا يمكن اعتباره صالحاً.')
    except Exception as exc:
        from app.infrastructure.artifact_storage import ArtifactStorageConfigurationError,ArtifactStorageError
        if isinstance(exc,(ArtifactStorageConfigurationError,ArtifactStorageError)):raise
        raise ValueError('تعذر فحص الملف محلياً. قد تكون أداة الفحص غير متاحة أو الملف غير قابل للقراءة. لم يُعدّل الأصل.') from exc
    blockers,pending=media_findings(platform,row.kind,info)
    # Do not return measurements as current if the source changed during the read.
    await session.refresh(row)
    await session.refresh(copy)
    if source_fingerprint(row)!=fingerprint or copy.version!=version: raise ValueError('تغير الأصل أو نسخة المنصة أثناء الفحص. أعد الفحص.')
    return {'inspected_media_id':media_id,'inspected_selection':selected,'artifact_id':str(uid),'platform':platform,'source_fingerprint':fingerprint,'copy_version':copy.version,'sha256':digest,'checked_at':datetime.now(timezone.utc).isoformat(),'measurements':info,'blockers':blockers,'pending':pending,'status':'BLOCKED' if blockers else 'MEASURED_WITH_PENDING_CHECKS','execution_authorized':False,'original_changed':False}


async def preview_instagram_jpeg(session,uid,platform,*,fingerprint,version,background):
    """Transient derivative only, deliberately not a new approved bank original."""
    import base64
    from app.domain.image_derivative import jpeg_preview
    row=await session.get(ArtifactModel,uid)
    copy=await session.get(PlatformCopyModel,(uid,platform))
    if platform not in {'instagram','facebook'} or row is None or row.kind!='IMAGE' or row.status!='AVAILABLE' or row.review_status!='APPROVED' or not row.storage_uri or copy is None:
        raise ValueError('اختر صورة أصلية معتمدة ونسخة Instagram أو Facebook مجهزة.')
    if source_fingerprint(row)!=fingerprint or copy.source_fingerprint!=fingerprint or copy.version!=version:
        raise ValueError('تغير الأصل أو النسخة. أعد تحميل النسخ قبل التحويل.')
    data=await S3ArtifactStorage.from_environment().get_bytes(row.storage_uri,max_bytes=50*1024*1024)
    try:content,info=await asyncio.to_thread(jpeg_preview,data,background)
    except ValueError as exc:raise ValueError(str(exc)) from exc
    except Exception as exc:raise ValueError('تعذر إنشاء JPEG آمن. لم يُغيّر الأصل أو تحفظ نسخة.') from exc
    await session.refresh(row);await session.refresh(copy)
    if source_fingerprint(row)!=fingerprint or copy.source_fingerprint!=fingerprint or copy.version!=version:
        raise ValueError('تغير الأصل أو النسخة أثناء التحويل. أعد المحاولة بعد المراجعة.')
    blockers,pending=media_findings(platform,'IMAGE',info)
    return {'artifact_id':str(uid),'source_fingerprint':fingerprint,'copy_version':version,'source_sha256':hashlib.sha256(data).hexdigest(),'sha256':hashlib.sha256(content).hexdigest(),'data_url':'data:image/jpeg;base64,'+base64.b64encode(content).decode('ascii'),'measurements':info,'blockers':blockers,'pending':pending,'execution_authorized':False,'original_changed':False,'persisted':False}
