"""Dormant resumable lifecycle. Not imported by routes or scheduler.

Caller authority remains an external gate, never implied by prepare. Bytes must
come from a future private pinned storage reader, not a user URL or preview.
"""

import hashlib, re
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.infrastructure.database.models import (
    YouTubeUploadModel as Job,
    ArtifactModel,
    PlatformCopyModel,
)
from app.application.distribution_readiness import source_fingerprint
from app.application.central_platform_copies import evaluate
from app.application.managed_connections import key
from app.adapters.publishing.youtube import CHANNEL, VIDEO, YouTubeProviderError


def now():
    return datetime.now(timezone.utc)


async def prepare(
    session,
    uid,
    *,
    channel_id,
    media_sha256,
    total_bytes,
    privacy,
    made_for_kids,
    contains_synthetic_media,
    category_id,
):
    if (
        not isinstance(channel_id, str)
        or not CHANNEL.fullmatch(channel_id)
        or not re.fullmatch(r"[a-f0-9]{64}", media_sha256)
    ):
        raise ValueError("Pinned channel and media required")
    if (
        isinstance(total_bytes, bool)
        or not isinstance(total_bytes, int)
        or not 0 < total_bytes <= 256 * 1024**3
    ):
        raise ValueError("Invalid byte count")
    if (
        privacy not in {"private", "unlisted", "public"}
        or not isinstance(made_for_kids, bool)
        or not isinstance(contains_synthetic_media, bool)
        or not isinstance(category_id, str)
        or not re.fullmatch("[0-9]{1,10}", category_id)
    ):
        raise ValueError("Explicit reviewed upload declarations required")
    row = (
        await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == uid).with_for_update()
        )
    ).scalar_one_or_none()
    copy = (
        await session.execute(
            select(PlatformCopyModel)
            .where(
                PlatformCopyModel.artifact_id == uid,
                PlatformCopyModel.platform == "youtube",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        row is None
        or copy is None
        or row.kind != "VIDEO"
        or evaluate(row, copy)["field_status"] != "FIELDS_VALIDATED"
    ):
        raise ValueError("Approved unchanged YouTube video copy required")
    snapshot = {
        **copy.fields,
        "category_id": category_id,
        "privacy": privacy,
        "made_for_kids": made_for_kids,
        "contains_synthetic_media": contains_synthetic_media,
        "mime_type": row.mime_type,
    }
    if (
        row.mime_type not in {"video/mp4", "video/quicktime"}
        or copy.selected_media_id is not None
    ):
        raise ValueError("This dormant core pins original MP4/MOV only")
    job = Job(
        artifact_id=uid,
        channel_id=channel_id,
        source_fingerprint=source_fingerprint(row),
        copy_version=copy.version,
        media_sha256=media_sha256,
        total_bytes=total_bytes,
        metadata_snapshot=snapshot,
        state="DRAFT",
        received_bytes=0,
        created_at=now(),
        updated_at=now(),
    )
    session.add(job)
    await session.commit()
    return job


async def locked(session, jid):
    job = (
        await session.execute(
            select(Job)
            .where(Job.id == jid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if job is None:
        raise ValueError("Upload record not found")
    return job


async def valid(session, job, provider, content):
    if (
        provider.channel_id != job.channel_id
        or not isinstance(content, bytes)
        or len(content) != job.total_bytes
        or hashlib.sha256(content).hexdigest() != job.media_sha256
    ):
        raise ValueError("Pinned channel or private bytes changed")
    row = (
        await session.execute(
            select(ArtifactModel)
            .where(ArtifactModel.id == job.artifact_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    copy = (
        await session.execute(
            select(PlatformCopyModel)
            .where(
                PlatformCopyModel.artifact_id == job.artifact_id,
                PlatformCopyModel.platform == "youtube",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if (
        row is None
        or copy is None
        or source_fingerprint(row) != job.source_fingerprint
        or copy.version != job.copy_version
        or copy.selected_media_id is not None
        or evaluate(row, copy)["field_status"] != "FIELDS_VALIDATED"
        or any(
            copy.fields[k] != job.metadata_snapshot[k]
            for k in ["title", "description", "tags", "alt_text"]
        )
    ):
        raise ValueError("Pinned original or metadata changed")


async def fail(session, job, error, state):
    if isinstance(error, YouTubeProviderError) and error.retry_after_seconds:
        job.retry_not_before = now() + timedelta(seconds=error.retry_after_seconds)
    job.state = state
    job.error_code = (
        error.code
        if isinstance(error, YouTubeProviderError)
        else "YOUTUBE_OUTCOME_UNKNOWN"
    )
    job.updated_at = now()
    await session.commit()
    return job


async def initiate(session, jid, *, provider, content, authorized=False):
    if authorized is not True:
        raise ValueError("Explicit owner upload authority required")
    crypt = key()
    job = await locked(session, jid)
    if job.state != "DRAFT":
        raise ValueError(
            "Session creation already claimed; never restart automatically"
        )
    await valid(session, job, provider, content)
    job.state = "INITIATING"
    job.updated_at = now()
    await session.commit()
    meta = job.metadata_snapshot
    try:
        uri = await provider.initiate(
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            category_id=meta["category_id"],
            privacy=meta["privacy"],
            made_for_kids=meta["made_for_kids"],
            contains_synthetic_media=meta["contains_synthetic_media"],
            total_bytes=job.total_bytes,
            mime_type=meta["mime_type"],
            authorized=True,
        )
        job.session_ciphertext = crypt.encrypt(uri.encode()).decode()
    except YouTubeProviderError as exc:
        return await fail(
            session, job, exc, "INIT_UNKNOWN" if exc.outcome_unknown else "FAILED"
        )
    except Exception as exc:
        return await fail(session, job, exc, "INIT_UNKNOWN")
    job.state = "SESSION_READY"
    job.updated_at = now()
    await session.commit()
    return job


async def send_next(
    session, jid, *, provider, content, authorized=False, chunk_bytes=256 * 1024
):
    if authorized is not True:
        raise ValueError("Explicit owner upload authority required")
    if (
        isinstance(chunk_bytes, bool)
        or not isinstance(chunk_bytes, int)
        or chunk_bytes <= 0
        or chunk_bytes > 8 * 1024 * 1024
        or chunk_bytes % (256 * 1024)
    ):
        raise ValueError("Bounded aligned chunk required")
    job = await locked(session, jid)
    if job.state not in {"SESSION_READY", "INCOMPLETE"}:
        raise ValueError("Upload needs reconciliation or is already complete")
    if job.retry_not_before and job.retry_not_before > now():
        raise ValueError("Provider Retry-After has not elapsed")
    await valid(session, job, provider, content)
    uri = key().decrypt(job.session_ciphertext.encode()).decode()
    start = job.received_bytes
    if start >= job.total_bytes:
        raise ValueError("All bytes reported received; reconcile before any send")
    chunk = content[start : start + chunk_bytes]
    job.state = "SENDING"
    job.updated_at = now()
    await session.commit()
    try:
        progress = await provider.upload_chunk(
            uri,
            chunk=chunk,
            start=start,
            total_bytes=job.total_bytes,
            mime_type=job.metadata_snapshot["mime_type"],
            authorized=True,
        )
    except Exception as exc:
        return await fail(session, job, exc, "UPLOAD_UNKNOWN")
    return await apply_progress(session, job, progress)


async def apply_progress(session, job, progress):
    if (
        progress.state not in {"SESSION_EXPIRED", "INCOMPLETE", "VIDEO_ID_KNOWN"}
        or type(progress.received_bytes) is not int
        or (
            progress.retry_after_seconds is not None
            and (
                type(progress.retry_after_seconds) is not int
                or not 0 <= progress.retry_after_seconds <= 999999999
            )
        )
    ):
        return await fail(session, job, ValueError(), "UPLOAD_UNKNOWN")
    if progress.state == "VIDEO_ID_KNOWN" and (
        progress.received_bytes != job.total_bytes
        or not isinstance(progress.video_id, str)
        or not VIDEO.fullmatch(progress.video_id)
    ):
        return await fail(session, job, ValueError(), "UPLOAD_UNKNOWN")
    if progress.state != "VIDEO_ID_KNOWN" and progress.video_id is not None:
        return await fail(session, job, ValueError(), "UPLOAD_UNKNOWN")
    if progress.state == "SESSION_EXPIRED":
        job.state = "SESSION_EXPIRED"
        job.updated_at = now()
        await session.commit()
        return job
    if (
        progress.received_bytes < job.received_bytes
        or progress.received_bytes > job.total_bytes
    ):
        return await fail(session, job, ValueError(), "UPLOAD_UNKNOWN")
    job.retry_not_before = (
        now() + timedelta(seconds=progress.retry_after_seconds)
        if progress.retry_after_seconds
        else None
    )
    job.received_bytes = progress.received_bytes
    job.video_id = progress.video_id
    job.state = progress.state
    job.error_code = None
    job.updated_at = now()
    await session.commit()
    return job


async def reconcile(session, jid, *, provider):
    job = await locked(session, jid)
    if (
        job.state not in {"UPLOAD_UNKNOWN", "INCOMPLETE", "SESSION_READY"}
        or provider.channel_id != job.channel_id
    ):
        raise ValueError("Only a stopped upload with a known session can be reconciled")
    if job.retry_not_before and job.retry_not_before > now():
        raise ValueError("Provider Retry-After has not elapsed")
    uri = key().decrypt(job.session_ciphertext.encode()).decode()
    # A persisted claim also serializes status probes with senders. A crashed
    # active claim needs explicit operator proof of worker termination.
    job.state = "CHECKING"
    job.updated_at = now()
    await session.commit()
    try:
        progress = await provider.status(uri, total_bytes=job.total_bytes)
    except Exception as exc:
        return await fail(session, job, exc, "UPLOAD_UNKNOWN")
    return await apply_progress(session, job, progress)


async def cancel_draft(session, jid):
    job = await locked(session, jid)
    if job.state != "DRAFT":
        raise ValueError("Only an unclaimed local draft can be cancelled")
    job.state = "CANCELLED"
    job.updated_at = now()
    await session.commit()
    return job


async def interrupted_claim(
    session, jid, *, expected_state, expected_updated_at, worker_confirmed_stopped=False
):
    if worker_confirmed_stopped is not True or expected_state not in {
        "INITIATING",
        "SENDING",
        "CHECKING",
        "VERIFYING",
    }:
        raise ValueError(
            "Operator must establish stopped worker; age alone is not evidence"
        )
    job = await locked(session, jid)
    if job.state != expected_state or job.updated_at != expected_updated_at:
        raise ValueError("Claim changed")
    job.state = (
        "INIT_UNKNOWN"
        if expected_state == "INITIATING"
        else "VIDEO_ID_KNOWN" if expected_state == "VERIFYING" else "UPLOAD_UNKNOWN"
    )
    job.error_code = "YOUTUBE_INTERRUPTED_CLAIM"
    job.updated_at = now()
    await session.commit()
    return job


async def verify_result(session, jid, *, provider):
    job = await locked(session, jid)
    if (
        job.state not in {"VIDEO_ID_KNOWN", "PROCESSING", "PROCESSED", "RESULT_CHANGED"}
        or not job.video_id
        or provider.channel_id != job.channel_id
    ):
        raise ValueError("Known selected-channel video required")
    job.state = "VERIFYING"
    job.updated_at = now()
    await session.commit()
    try:
        result = await provider.video_status(job.video_id)
    except Exception as exc:
        return await fail(session, job, exc, "VIDEO_ID_KNOWN")
    if (
        result["video_id"] != job.video_id
        or result["channel_id"] != job.channel_id
        or result["privacy"] != job.metadata_snapshot["privacy"]
    ):
        job.state = "RESULT_CHANGED"
    elif result["upload_status"] in {"failed", "rejected", "deleted"} or result[
        "processing_status"
    ] in {"failed", "terminated"}:
        job.state = "FAILED"
    elif (
        result["upload_status"] == "processed"
        and result["processing_status"] == "succeeded"
    ):
        job.state = "PROCESSED"
    else:
        job.state = "PROCESSING"
    job.updated_at = now()
    await session.commit()
    return job
