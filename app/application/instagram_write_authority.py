"""Unregistered authoritative due-write guard, not a claim or activation gate.

Caller owns an explicit transaction and must hold the future shared fence first.
This helper never commits, mints controls/grants, or invokes a provider. Returned
ORM rows are transaction-local internal data, not an API response/capability.
"""
import re
from datetime import datetime
from sqlalchemy import select, text
from app.infrastructure.database.models import (
    InstagramDispatchModel as Dispatch, InstagramExecutionModel as Job,
    InstagramPublishDecisionModel as Decision, InstagramMediaGrantModel as Grant,
    ArtifactModel as Artifact, PlatformCopyModel as Copy,
    DistributionSelectionModel as Selection, InstagramPlanDraftModel as Review,
    InstagramConnectionModel as Connection, PlatformMediaInspectionModel as Inspection)
from app.application import instagram_publish_decisions as decisions
from app.application.instagram_plan_review import fingerprint
from app.application.distribution_readiness import source_fingerprint
from app.application.instagram_media_pin import recheck_pinned_bytes
from app.application.central_platform_copies import evaluate


async def _one(session, model, condition):
    value = await session.scalar(select(model).where(condition).with_for_update(nowait=True)
        .execution_options(populate_existing=True))
    if value is None:
        raise ValueError('Missing authoritative write record')
    return value


def _clock(dispatch, decision, grant):
    at = decisions.now()
    due = datetime.fromisoformat(decision.snapshot['due_at'])
    if (due != dispatch.due_at or due > at or decision.expires_at <= at
            or grant.expires_at <= at or grant.created_at < due
            or grant.expires_at > decision.expires_at
            or (grant.expires_at - grant.created_at).total_seconds() > 900):
        raise ValueError('Exact due window or bounded grant expired')


async def validate_locked(session, dispatch_id, *, step, grant_id):
    """Validate authoritative rows only; does not confer write permission.

    No fresh-session convenience wrapper: a future production claim command must
    call this inside the SAME fence/claim transaction and commit all together.
    No caller exists in this candidate, and PRIVATE_BATCH_UNIFIED is rejected.
    """
    from sqlalchemy.orm import SessionTransactionOrigin
    transaction = session.sync_session.get_transaction()
    if (transaction is None or transaction.origin is not SessionTransactionOrigin.BEGIN
            or step not in {'CREATE_CONTAINER', 'PUBLISH'}):
        raise ValueError('Owned transaction and exact provider write step required')
    try:
        dispatch = await _one(session, Dispatch, Dispatch.id == dispatch_id)
        job = await _one(session, Job, Job.id == dispatch.execution_id)
        decision = await _one(session, Decision, Decision.id == dispatch.decision_id)
        original = await _one(session, Artifact, Artifact.id == job.artifact_id)
        copy = await _one(session, Copy, (Copy.artifact_id == job.artifact_id) & (Copy.platform == 'instagram'))
        selection = await _one(session, Selection, Selection.artifact_id == job.artifact_id)
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(606024)')):
            raise ValueError('Account lifecycle busy')
        await _one(session, Connection, Connection.id == 1)
        binding = job.connection_binding
        if binding.get('login_mode') != 'UNIFIED':
            raise ValueError('Only existing individual Unified provenance supported; batch remains disabled')
        from uuid import UUID
        review = await _one(session, Review, Review.id == UUID(binding['review_id']))
        await _one(session, Inspection, Inspection.id == job.inspection_id)
        grant = await _one(session, Grant, Grant.id == grant_id)
        if step == 'CREATE_CONTAINER':
            valid_state = dispatch.state in {'PENDING', 'CLAIMED'} and job.state == 'DRAFT' and not job.container_id and not job.media_id
        else:
            valid_state = dispatch.state in {'CLAIMED', 'WAITING_MEDIA'} and job.state in {'CONTAINER_CREATED', 'WAITING_MEDIA'} and bool(job.container_id) and not job.media_id
        if not valid_state:
            raise ValueError('Step already attempted or incompatible dispatch state')
        if (decision.execution_id != job.id or decision.state != 'APPROVED'
                or not re.fullmatch(r'(owner-session|trusted-message):[A-Za-z0-9_.:-]{8,240}', decision.evidence_ref)
                or fingerprint(decision.snapshot) != decision.snapshot_hash
                or decision.snapshot.get('audience') != 'INSTAGRAM_PUBLIC_POST'
                or decision.snapshot.get('media_disclosure') != 'BEARER_LINK_READABLE_FOR_META_15_MINUTES'
                or review.state != 'DRAFT' or review.snapshot_hash != binding['review_hash']
                or grant.execution_id != job.id or grant.decision_id != decision.id
                or grant.state != 'ACTIVE' or grant.sha256 != job.media_sha256
                or grant.reads >= 20):
            raise ValueError('Exact decision, review or grant binding is unavailable')
        fp = source_fingerprint(original)
        if (original.review_status != 'APPROVED' or original.status != 'AVAILABLE'
                or original.kind not in {'IMAGE', 'VIDEO'} or original.kind != job.kind
                or fp != job.source_fingerprint or copy.source_fingerprint != fp
                or copy.version != job.copy_version or copy.fields.get('description') != job.caption
                or copy.fields.get('alt_text') != job.alt_text or evaluate(original, copy)['field_status'] != 'FIELDS_VALIDATED'
                or selection.source_fingerprint != fp or 'instagram' not in selection.platforms):
            raise ValueError('Original, exact copy or saved destination changed')
        _clock(dispatch, decision, grant)
        await decisions.validate(session, job, decision.id)
        # These reads are private and may be slow. All authoritative row locks
        # remain held. Recheck authority and the clock again after they return.
        await recheck_pinned_bytes(session, job)
        await decisions.validate(session, job, decision.id)
        _clock(dispatch, decision, grant)
        return dispatch, job, decision, grant
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError('Malformed authority; provider write blocked') from exc
