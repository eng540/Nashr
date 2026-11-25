"""Dormant, non-runnable Page attempt lifecycle. No routes or scheduler imports.

Caller still owes account/permission/rights/inspection and publication approval.
No URL exposure, implicit retries, token persistence or account changes here.
"""
import hashlib
import re
from datetime import datetime, timezone
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel, PlatformCopyModel, FacebookExecutionModel as Job
from app.application.distribution_readiness import source_fingerprint
from app.adapters.publishing.facebook import ID, FacebookPagePublisher, FacebookProviderError


def now():
    return datetime.now(timezone.utc)


async def original(session, uid):
    row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == uid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    copy = (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id == uid, PlatformCopyModel.platform == 'facebook').with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None or copy is None or row.review_status != 'APPROVED' or row.status != 'AVAILABLE' or row.kind not in {'TEXT','IMAGE'}:
        raise ValueError('Approved original text or photo and saved Page copy required')
    if source_fingerprint(row) != copy.source_fingerprint or copy.selected_media_id is not None:
        raise ValueError('Changed source or derived media not supported in dormant core')
    from app.application.facebook_copy_fields import blockers
    reasons=blockers(row.kind,copy.fields)
    if reasons:raise ValueError('; '.join(reasons))
    return row, copy


async def prepare(session, uid, *, page_id, media_sha256=None, total_bytes=0):
    if not isinstance(page_id, str) or not ID.fullmatch(page_id):
        raise ValueError('Explicit proposed Page required')
    row, copy = await original(session, uid)
    if row.kind == 'IMAGE':
        if row.mime_type not in {'image/jpeg','image/png'} or not isinstance(media_sha256,str) or not re.fullmatch('[a-f0-9]{64}',media_sha256) or type(total_bytes) is not int or not 0 < total_bytes <= 4_000_000:
            raise ValueError('Pinned original JPEG/PNG digest and byte count required')
    elif media_sha256 is not None or type(total_bytes) is not int or total_bytes != 0:
        raise ValueError('Text attempt cannot carry media')
    job = Job(artifact_id=uid, page_id=page_id, source_fingerprint=source_fingerprint(row), copy_version=copy.version, kind=row.kind, message=copy.fields['description'], mime_type=row.mime_type if row.kind == 'IMAGE' else None, media_sha256=media_sha256, total_bytes=total_bytes, state='DRAFT', created_at=now(), updated_at=now())
    session.add(job)
    await session.commit()
    return job


async def locked(session,jid):
    job=(await session.execute(select(Job).where(Job.id == jid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if job is None:
        raise ValueError('Page attempt not found')
    return job


async def publish(session,jid,*,provider,content=None,authorized=False,public_page_acknowledged=False,rights_confirmed=False,prerequisites_verified=False):
    if not all(x is True for x in [authorized,public_page_acknowledged,rights_confirmed,prerequisites_verified]):
        raise ValueError('Verified prerequisites and explicit public Page publication authority required')
    job=await locked(session,jid)
    if job.state != 'DRAFT':
        raise ValueError('Attempt already claimed; no automatic resubmission')
    row,copy=await original(session,job.artifact_id)
    if provider.page_id != job.page_id or source_fingerprint(row) != job.source_fingerprint or copy.version != job.copy_version or copy.fields['description'] != job.message or row.kind != job.kind or (job.kind == 'IMAGE' and row.mime_type != job.mime_type):
        raise ValueError('Pinned source, Page or exact copy changed')
    if job.kind == 'IMAGE':
        if not isinstance(content,bytes) or len(content) != job.total_bytes or hashlib.sha256(content).hexdigest() != job.media_sha256:
            raise ValueError('Private pinned bytes changed')
    elif content is not None:
        raise ValueError('Text cannot disclose media bytes')
    # Commit before external effect. Crash or unknown response never retries.
    job.state='SENDING';job.updated_at=now();await session.commit()
    try:
        if job.kind == 'TEXT':
            result=await provider.publish_text(message=job.message,authorized=True,public_page_acknowledged=True)
        else:
            result=await provider.publish_photo(message=job.message,content=content,mime_type=job.mime_type,sha256=job.media_sha256,authorized=True,public_page_acknowledged=True)
        # Independently fence even a malformed/incomplete adapter result.
        if result.state != 'POST_ID_KNOWN' or not isinstance(result.post_id,str) or not re.fullmatch(re.escape(job.page_id)+r'_[0-9]{1,100}',result.post_id):
            raise ValueError('Unverified post result')
        job.post_id=result.post_id;job.photo_id=result.photo_id;job.state='POST_ID_KNOWN';job.error_code=None
    except Exception as exc:
        job.state='OUTCOME_UNKNOWN' if not isinstance(exc,FacebookProviderError) or exc.outcome_unknown else 'FAILED'
        job.error_code=exc.code if isinstance(exc,FacebookProviderError) else 'FACEBOOK_OUTCOME_UNKNOWN'
    job.updated_at=now();await session.commit();return job


async def reconcile(session,jid,*,provider):
    job=await locked(session,jid)
    if provider.page_id != job.page_id or not job.post_id or job.state in {'DRAFT','CANCELLED','SENDING'}:
        raise ValueError('Known result identity and no active mutation required')
    # Readback may run after local edits. It reports provider truth, not consent.
    result=await provider.verify_post(job.post_id,expected_message=job.message)
    if result.post_id != job.post_id or result.state not in {'RESULT_CHANGED','NOT_CONFIRMED_PUBLISHED','PUBLISHED_AT_LAST_CHECK'}:
        raise ValueError('Provider result mismatch')
    job.state=result.state;job.permalink=result.permalink;job.updated_at=now();await session.commit();return job


async def cancel_draft(session,jid):
    job=await locked(session,jid)
    if job.state != 'DRAFT':
        raise ValueError('Cannot undo a provider attempt by local cancellation')
    job.state='CANCELLED';job.updated_at=now();await session.commit();return job


async def interrupted_claim(session,jid,*,expected_updated_at,worker_confirmed_stopped=False):
    if worker_confirmed_stopped is not True:
        raise ValueError('Worker stopped must be established; age alone is not evidence')
    job=await locked(session,jid)
    if job.state != 'SENDING' or job.updated_at != expected_updated_at:
        raise ValueError('Claim changed; reread it')
    job.state='OUTCOME_UNKNOWN';job.error_code='FACEBOOK_INTERRUPTED_CLAIM_UNKNOWN';job.updated_at=now();await session.commit();return job
