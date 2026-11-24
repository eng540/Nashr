"""Pin private measured bytes. No provider URL or publication authority is created."""
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel, PlatformCopyModel, PlatformMediaInspectionModel
from app.application.distribution_readiness import source_fingerprint
from app.application.media_inspection_history import PROBE_VERSION
from app.application.platform_media_probe import probe_platform_media


async def inspection_for_copy(session, uid, inspection_id, *, fingerprint, copy_version):
    row = (await session.execute(select(ArtifactModel).where(ArtifactModel.id == uid)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    copy = (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id == uid,
        PlatformCopyModel.platform == 'instagram').with_for_update()
        .execution_options(populate_existing=True))).scalar_one_or_none()
    record = await session.get(PlatformMediaInspectionModel, inspection_id, populate_existing=True)
    if row is None or copy is None or record is None:
        raise ValueError('A saved Instagram inspection of this copy is required')
    if (record.artifact_id != uid or record.platform != 'instagram' or
        record.source_fingerprint != fingerprint or record.copy_version != copy_version or
        record.probe_version != PROBE_VERSION or source_fingerprint(row) != fingerprint or
        copy.source_fingerprint != fingerprint or copy.version != copy_version or
        row.review_status != 'APPROVED' or row.status != 'AVAILABLE'):
        raise ValueError('Inspection, original or copy changed')
    # Pin the selected path explicitly, including an explicit original selection.
    if record.selected is not True or record.media_id != copy.selected_media_id:
        raise ValueError('Inspection must match the current selected media')
    result = record.result
    if (result.get('artifact_id') != str(uid) or result.get('platform') != 'instagram' or
        result.get('source_fingerprint') != fingerprint or result.get('copy_version') != copy_version or
        result.get('sha256') != record.sha256 or result.get('inspected_selection') is not True or
        result.get('inspected_media_id') != (str(copy.selected_media_id) if copy.selected_media_id else None) or
        result.get('status') != 'MEASURED_WITH_PENDING_CHECKS' or result.get('blockers') != []):
        raise ValueError('Inspection is blocked or its evidence does not match')
    return record


async def recheck_pinned_bytes(session, job):
    if job.inspection_id is None:
        raise ValueError('Uninspected synthetic draft cannot call a provider')
    record = await inspection_for_copy(session, job.artifact_id, job.inspection_id,
        fingerprint=job.source_fingerprint, copy_version=job.copy_version)
    result = await probe_platform_media(session, job.artifact_id, 'instagram', selected=True)
    # The saved record is historical evidence, never a substitute for reading bytes.
    if (result['sha256'] != job.media_sha256 or record.sha256 != job.media_sha256 or
        result.get('inspected_media_id') != (str(record.media_id) if record.media_id else None) or
        result['blockers'] or result['status'] != 'MEASURED_WITH_PENDING_CHECKS'):
        raise ValueError('Current private media differs or is blocked; no provider call')
    return result
