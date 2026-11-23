"""Read-only, explicit inspection of private original bytes."""
import asyncio
import hashlib
from datetime import datetime,timezone
from app.application.distribution_readiness import source_fingerprint
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.domain.platform_media_probe import inspect_media,media_findings


async def probe_platform_media(session,uid,platform):
    row=await session.get(ArtifactModel,uid)
    if row is None or row.status!='AVAILABLE' or row.review_status!='APPROVED' or row.kind not in {'IMAGE','VIDEO'} or not row.storage_uri:
        raise ValueError('اختر صورة أو فيديو أصلياً معتمداً ومتاحاً.')
    copy=await session.get(PlatformCopyModel,(uid,platform))
    if copy is None: raise ValueError('جهّز نسخة المنصة أولاً.')
    fingerprint=source_fingerprint(row)
    version=copy.version
    if copy.source_fingerprint!=fingerprint: raise ValueError('تغير الأصل منذ تجهيز النسخة. راجعها أولاً.')
    data=await S3ArtifactStorage.from_environment().get_bytes(row.storage_uri,max_bytes=50*1024*1024)
    try:
        info=await asyncio.to_thread(inspect_media,data,row.kind,row.mime_type)
    except Exception as exc:
        # A missing probe binary or unreadable media is unverified, never a pass.
        raise ValueError('تعذر فحص الملف محلياً. قد تكون أداة الفحص غير متاحة أو الملف غير قابل للقراءة. لم يُعدّل الأصل.') from exc
    blockers,pending=media_findings(platform,row.kind,info)
    # Do not return measurements as current if the source changed during the read.
    await session.refresh(row)
    await session.refresh(copy)
    if source_fingerprint(row)!=fingerprint or copy.version!=version: raise ValueError('تغير الأصل أو نسخة المنصة أثناء الفحص. أعد الفحص.')
    return {'artifact_id':str(uid),'platform':platform,'source_fingerprint':fingerprint,'copy_version':copy.version,'sha256':hashlib.sha256(data).hexdigest(),'checked_at':datetime.now(timezone.utc).isoformat(),'measurements':info,'blockers':blockers,'pending':pending,'status':'BLOCKED' if blockers else 'MEASURED_WITH_PENDING_CHECKS','execution_authorized':False,'original_changed':False}
