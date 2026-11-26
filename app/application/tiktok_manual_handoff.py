"""Private export for the owner. Never calls TikTok or records publication."""
import hashlib
import io
import json
import zipfile
from sqlalchemy import select
from app.application.distribution_readiness import source_fingerprint
from app.infrastructure.database.models import ArtifactModel, PlatformCopyModel
from app.infrastructure.artifact_storage import S3ArtifactStorage

MAX_BYTES = 50 * 1024 * 1024

async def snapshot(session, uid, version, fingerprint):
    row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == uid).execution_options(populate_existing=True))).scalar_one_or_none()
    copy = (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id == uid, PlatformCopyModel.platform == 'tiktok').execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None or copy is None or row.review_status != 'APPROVED' or row.status != 'AVAILABLE':
        raise ValueError('اختر فيديو معتمدًا ونسخة TikTok محفوظة.')
    if row.kind != 'VIDEO' or row.mime_type not in {'video/mp4', 'video/quicktime'} or not row.storage_uri:
        raise ValueError('الحزمة اليدوية تدعم أصل فيديو MP4 أو MOV فقط، دون تحويل.')
    if source_fingerprint(row) != fingerprint or copy.source_fingerprint != fingerprint or copy.version != version:
        raise ValueError('تغير الأصل أو نسخة TikTok. أعد تحميلها وراجعها قبل التنزيل.')
    if copy.selected_media_id is not None:
        raise ValueError('يوجد وسيط مختار لا يدعمه هذا التصدير. لم نستبدله بالأصل صامتًا.')
    fields = dict(copy.fields)
    if not isinstance(fields.get('description'), str):
        raise ValueError('تعذر قراءة الوصف المحفوظ.')
    return row.storage_uri, row.mime_type, fields

async def export_bundle(session, uid, version, fingerprint):
    before = await snapshot(session, uid, version, fingerprint)
    data = await S3ArtifactStorage.from_environment().get_bytes(before[0], max_bytes=MAX_BYTES)
    if not data or len(data) > MAX_BYTES:
        raise ValueError('حد حزمة التنزيل المحلية 50MiB. لم يُقص الملف أو يُرفع.')
    # Storage reading can take time. Recheck all current source and copy facts.
    await session.rollback()
    after = await snapshot(session, uid, version, fingerprint)
    if before != after:
        raise ValueError('تغيرت الحقول أو الوسيط أثناء التجهيز. لم تُجهز حزمة قديمة.')
    ext = 'mp4' if before[1] == 'video/mp4' else 'mov'
    filename = 'video-original.' + ext
    manifest = dict(artifact_id=str(uid), platform='tiktok', copy_version=version,
                    source_fingerprint=fingerprint, media_filename=filename,
                    media_sha256=hashlib.sha256(data).hexdigest(), original_unchanged=True,
                    upload_performed=False, publication_recorded=False, execution_authorized=False,
                    caption_source='saved TikTok description, unchanged',
                    separate_fields={k: v for k, v in before[2].items() if k != 'description'},
                    caveat='حزمة محلية للرفع اليدوي فقط. ليست قبول TikTok للملف أو الوصف أو الحقوق. الحقول المنفصلة محفوظة في البيان ولا تُلصق بالوصف.')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr(filename, data)
        bundle.writestr('caption.txt', before[2]['description'].encode('utf-8'))
        bundle.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
        bundle.writestr('README.txt', 'هذه حزمة خاصة لتنزيلك، لم يُرسل شيء إلى TikTok.\nراجع الفيديو والوصف والحقوق والجمهور داخل TikTok قبل أي رفع أو نشر.\nالفيديو هو الأصل دون تحويل. الوصف هو نسخة TikTok المحفوظة دون قص.\nالعنوان والوسوم والنص البديل المنفصلة في manifest.json ولا تضاف إلى caption.txt تلقائيًا.\nهذه الحزمة ليست دليل نشر أو جاهزية نهائية.\n'.encode('utf-8'))
    return output.getvalue()
