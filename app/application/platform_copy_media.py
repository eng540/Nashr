"""Explicit private derivative selection, never publication or source edits."""
import asyncio
import hashlib
from datetime import datetime,timezone
from uuid import uuid4
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,PlatformCopyMediaModel
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.application.distribution_readiness import source_fingerprint
from app.domain.image_derivative import jpeg_preview


def describe_media(row,asset):
    return {'id':str(asset.id),'platform':asset.platform,'source_fingerprint':asset.source_fingerprint,
        'source_stale':asset.source_fingerprint!=source_fingerprint(row),'mime_type':asset.mime_type,
        'sha256':asset.sha256,'source_sha256':asset.source_sha256,'recipe':asset.recipe,
        'measurements':asset.measurements,'created_at':asset.created_at.isoformat() if asset.created_at else None}


async def current_copy(session,uid,platform,fingerprint,version,allow_stale_copy=False):
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())).scalar_one_or_none()
    copy=(await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==uid,PlatformCopyModel.platform==platform).with_for_update())).scalar_one_or_none()
    if row is None or copy is None or row.review_status!='APPROVED' or row.status!='AVAILABLE':
        raise ValueError('اختر أصلاً معتمداً ونسخة منصة مجهزة.')
    if source_fingerprint(row)!=fingerprint or (not allow_stale_copy and copy.source_fingerprint!=fingerprint) or copy.version!=version:
        raise ValueError('تغير الأصل أو النسخة. أعد تحميلها قبل اختيار الوسيط.')
    return row,copy


async def list_media(session,uid,platform):
    row=await session.get(ArtifactModel,uid);copy=await session.get(PlatformCopyModel,(uid,platform))
    if row is None or copy is None:raise ValueError('جهّز النسخة أولاً.')
    assets=(await session.execute(select(PlatformCopyMediaModel).where(PlatformCopyMediaModel.artifact_id==uid,PlatformCopyMediaModel.platform==platform).order_by(PlatformCopyMediaModel.created_at.desc()).limit(30))).scalars().all()
    if copy.selected_media_id and not any(a.id==copy.selected_media_id for a in assets):
        current=await session.get(PlatformCopyMediaModel,copy.selected_media_id)
        if current is not None and current.artifact_id==uid and current.platform==platform:assets.append(current)
    return {'selected_media_id':str(copy.selected_media_id) if copy.selected_media_id else None,'copy_version':copy.version,
        'source_fingerprint':source_fingerprint(row),'items':[describe_media(row,asset) for asset in assets],
        'execution_authorized':False,'caveat':'وسائط خاصة محفوظة للتجهيز. لا جدول أو إذن نشر من اختيارها. يعرض آخر30نسخة.'}


async def save_jpeg(session,uid,platform,*,fingerprint,version,background,expected_sha256):
    if platform not in {'instagram','facebook'}:raise ValueError('تحويل JPEG المحفوظ لنسخة Instagram أو Facebook فقط.')
    row,copy=await current_copy(session,uid,platform,fingerprint,version)
    if row.kind!='IMAGE' or not row.storage_uri:raise ValueError('اختر صورة أصلية مخزنة.')
    storage=S3ArtifactStorage.from_environment()
    data=await storage.get_bytes(row.storage_uri,max_bytes=50*1024*1024)
    try:content,measurements=await asyncio.to_thread(jpeg_preview,data,background)
    except ValueError:raise
    except Exception as exc:raise ValueError('تعذر تحويل الصورة. لم يُغيّر الأصل أو الاختيار.') from exc
    digest=hashlib.sha256(content).hexdigest()
    if digest!=expected_sha256:raise ValueError('اختلفت نتيجة التحويل عن المعاينة التي راجعتها. أنشئ معاينة جديدة أولاً.')
    recipe={'kind':platform.upper()+'_JPEG','version':1,'background':background,'quality':90,'cropped':False}
    # Retry after an ambiguous response can reuse immutable bytes instead of uploading again.
    existing=(await session.execute(select(PlatformCopyMediaModel).where(PlatformCopyMediaModel.artifact_id==uid,PlatformCopyMediaModel.platform==platform,PlatformCopyMediaModel.source_fingerprint==fingerprint,PlatformCopyMediaModel.sha256==digest,PlatformCopyMediaModel.recipe==recipe))).scalars().first()
    uploaded_uri=None
    if existing is None:
        asset_id=uuid4()
        uri=await storage.put(key=f'artifacts/platform-copies/{uid}/{platform}/{asset_id}.jpg',content=content,content_type='image/jpeg')
        uploaded_uri=uri
        existing=PlatformCopyMediaModel(id=asset_id,artifact_id=uid,platform=platform,source_fingerprint=fingerprint,source_sha256=hashlib.sha256(data).hexdigest(),sha256=digest,storage_uri=uri,mime_type='image/jpeg',recipe=recipe,measurements=measurements)
        session.add(existing)
    copy.selected_media_id=existing.id;copy.version+=1;copy.updated_at=datetime.now(timezone.utc)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        if uploaded_uri:
            import logging
            logging.getLogger(__name__).exception('Private derivative storage write preceded a database error; retained bytes for reconciliation, never deleting after an ambiguous commit.')
        raise
    return {'media':describe_media(row,existing),'copy_version':copy.version,'selected_media_id':str(existing.id),'execution_authorized':False,'original_changed':False}


async def select_media(session,uid,platform,*,fingerprint,version,media_id):
    row,copy=await current_copy(session,uid,platform,fingerprint,version,allow_stale_copy=media_id is None)
    if platform=='telegram':raise ValueError('اختيار وسيط مشتق لـTelegram غير متاح؛ خططه الحالية محفوظة دون تغيير.')
    if media_id is not None:
        asset=await session.get(PlatformCopyMediaModel,media_id)
        if asset is None or asset.artifact_id!=uid or asset.platform!=platform:raise ValueError('الوسيط لا يتبع هذه المادة ونسخة المنصة.')
        if asset.source_fingerprint!=fingerprint:raise ValueError('الوسيط مشتق من أصل قديم. أعد تجهيزه أولاً.')
    copy.selected_media_id=media_id;copy.version+=1;copy.updated_at=datetime.now(timezone.utc)
    await session.commit()
    return {'selected_media_id':str(media_id) if media_id else None,'copy_version':copy.version,'execution_authorized':False,'original_changed':False}


async def media_url(session,uid,platform,media_id):
    row=await session.get(ArtifactModel,uid);asset=await session.get(PlatformCopyMediaModel,media_id)
    if row is None or asset is None or asset.artifact_id!=uid or asset.platform!=platform:
        raise ValueError('الوسيط لا يتبع هذه المادة ونسخة المنصة.')
    # Reviewing stale history is allowed, but it remains explicitly stale and cannot be selected.
    url=await S3ArtifactStorage.from_environment().presign_get(asset.storage_uri,expires_seconds=300)
    return {'url':url,'expires_in':300,**describe_media(row,asset),'execution_authorized':False}


async def prepare_video(session,uid,platform,*,fingerprint,version):
    """Explicit private format preparation; no new Artifact or execution decision."""
    from app.domain.video_derivative import video_derivative
    if platform not in {'instagram','facebook'}:raise ValueError('نسخ الفيديو لـInstagram وFacebook فقط.')
    row=await session.get(ArtifactModel,uid);copy=await session.get(PlatformCopyModel,(uid,platform))
    if row is None or copy is None or row.review_status!='APPROVED' or row.status!='AVAILABLE' or source_fingerprint(row)!=fingerprint or copy.source_fingerprint!=fingerprint or copy.version!=version:
        raise ValueError('تغير الأصل أو نسخة المنصة؛ أعد تحميلها.')
    if row.kind!='VIDEO' or row.mime_type not in {'video/mp4','video/quicktime'} or not row.storage_uri:
        raise ValueError('اختر فيديوMP4/MOVأصلياً معتمداً.')
    storage=S3ArtifactStorage.from_environment()
    source=await storage.get_bytes(row.storage_uri,max_bytes=50_000_000)
    try:content,measurements=await asyncio.to_thread(video_derivative,source,platform)
    except ValueError:raise
    except Exception as exc:raise ValueError('تعذر تجهيز نسخة فيديو آمنة. الأصل والاختيار لم يتغيرا.') from exc
    # Conversion has no row locks. Serialize only the final save, then re-read.
    row,copy=await current_copy(session,uid,platform,fingerprint,version)
    await session.refresh(row);await session.refresh(copy)
    if source_fingerprint(row)!=fingerprint or copy.source_fingerprint!=fingerprint or copy.version!=version or row.review_status!='APPROVED' or row.status!='AVAILABLE':
        raise ValueError('تغير الأصل أو نسخة المنصة أثناء التحويل.')
    recipe={'kind':'FULL_FRAME_VIDEO','version':1,'platform':platform,'canvas':'1080x1920','padding':'black','cropped':False,'trimmed':False,'audio':'AAC_STEREO_48K_'+('120K' if platform=='instagram' else '160K')}
    digest=hashlib.sha256(content).hexdigest()
    existing=(await session.execute(select(PlatformCopyMediaModel).where(PlatformCopyMediaModel.artifact_id==uid,PlatformCopyMediaModel.platform==platform,PlatformCopyMediaModel.source_fingerprint==fingerprint,PlatformCopyMediaModel.sha256==digest,PlatformCopyMediaModel.recipe==recipe))).scalars().first()
    if existing is None:
        mid=uuid4();uri=await storage.put(key=f'artifacts/platform-copies/{uid}/{platform}/{mid}.mp4',content=content,content_type='video/mp4')
        existing=PlatformCopyMediaModel(id=mid,artifact_id=uid,platform=platform,source_fingerprint=fingerprint,source_sha256=hashlib.sha256(source).hexdigest(),sha256=digest,storage_uri=uri,mime_type='video/mp4',recipe=recipe,measurements=measurements);session.add(existing)
    # Save for explicit visual review only. Selection requires its own version-bound action.
    await session.commit()
    return {'media':describe_media(row,existing),'copy_version':copy.version,'selected_media_id':str(copy.selected_media_id) if copy.selected_media_id else None,'execution_authorized':False,'original_changed':False,'selected':False}
