"""Exact decision mechanics. No production route records a decision yet.

An authenticated future command must supply the user's actual approval and
source reference. Boolean parameters are not evidence by themselves.
"""
import re
from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from app.infrastructure.database.models import InstagramExecutionModel as Job,InstagramPublishDecisionModel as Decision,InstagramMediaGrantModel as Grant,InstagramDispatchModel as Dispatch
from app.application import instagram_direct_execution as direct
from app.application.instagram_plan_review import fingerprint


def now():return datetime.now(timezone.utc)

def snapshot(job,*,due_at,timezone_name):
    from zoneinfo import ZoneInfo
    if due_at.tzinfo is None:raise ValueError('Timezone-aware exact publication time required')
    zone=ZoneInfo(timezone_name)
    return dict(execution_id=str(job.id),artifact_id=str(job.artifact_id),account_id=job.account_id,
        username=job.connection_binding['username'],connection_binding=job.connection_binding,
        kind=job.kind,caption=job.caption,alt_text=job.alt_text,share_to_feed=job.share_to_feed,
        media_sha256=job.media_sha256,inspection_id=str(job.inspection_id),copy_version=job.copy_version,
        source_fingerprint=job.source_fingerprint,due_at=due_at.astimezone(timezone.utc).isoformat(),
        timezone=timezone_name,local_time=due_at.astimezone(zone).isoformat(),
        audience='INSTAGRAM_PUBLIC_POST',media_disclosure='BEARER_LINK_READABLE_FOR_META_15_MINUTES',
        disclosure_caveat='Anyone holding the temporary bearer link can read the exact media until expiry or revocation. Meta may retain its own copy.',
        scheduled=False,approval_recorded=False)

async def proposal(session,jid,*,due_at,timezone_name):
    job=await session.get(Job,jid,populate_existing=True)
    if not job or job.state!='DRAFT':raise ValueError('Unclaimed direct execution draft required')
    await direct.validate_binding(session,job)
    value=snapshot(job,due_at=due_at,timezone_name=timezone_name)
    return {**value,'decision_hash':fingerprint(value),'execution_enabled':False,'media_exposure_enabled':False}

async def record(session,jid,*,decision_hash,due_at,timezone_name,evidence_ref,authenticated_owner=False,
                 exact_words_approved=False,public_post_approved=False,media_disclosure_approved=False):
    if any(x is not True for x in [authenticated_owner,exact_words_approved,public_post_approved,media_disclosure_approved]):raise ValueError('Exact owner approval of account, words, media, audience, time and disclosure required')
    if not isinstance(evidence_ref,str) or not re.fullmatch(r'(?:owner-session|trusted-message):[A-Za-z0-9_.:-]{8,240}',evidence_ref):raise ValueError('Authenticated decision source reference required')
    job=(await session.execute(select(Job).where(Job.id==jid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not job or job.state!='DRAFT':raise ValueError('Unclaimed draft required')
    await direct.validate_binding(session,job)
    value=snapshot(job,due_at=due_at,timezone_name=timezone_name)
    if due_at<=now() or due_at>now()+timedelta(days=7) or fingerprint(value)!=decision_hash:raise ValueError('Decision changed, elapsed or outside seven-day dispatch window')
    old=(await session.execute(select(Decision).where(Decision.execution_id==jid,Decision.state=='APPROVED'))).scalars().first()
    if old:
        if old.snapshot_hash!=decision_hash:raise ValueError('Revoke earlier decision before replacing it')
        return old
    row=Decision(execution_id=jid,snapshot_hash=decision_hash,snapshot=value,evidence_ref=evidence_ref,state='APPROVED',created_at=now(),expires_at=due_at+timedelta(minutes=15))
    session.add(row);await session.commit();return row

async def validate(session,job,decision_id,*,at=None):
    decision=await session.get(Decision,decision_id,populate_existing=True);at=at or now()
    if not decision or decision.execution_id!=job.id or decision.state!='APPROVED' or decision.expires_at<=at:raise ValueError('Decision absent, expired or revoked')
    await session.refresh(job)
    s=decision.snapshot
    if fingerprint(snapshot(job,due_at=datetime.fromisoformat(s['due_at']),timezone_name=s['timezone']))!=decision.snapshot_hash:raise ValueError('Exact approved publication changed')
    await direct.validate_binding(session,job)
    return decision

async def revoke(session,decision_id):
    decision=(await session.execute(select(Decision).where(Decision.id==decision_id).with_for_update())).scalar_one_or_none()
    if not decision:raise ValueError('Decision not found')
    decision.state='REVOKED'
    for row in (await session.execute(select(Grant).where(Grant.decision_id==decision_id))).scalars():row.state='REVOKED'
    for row in (await session.execute(select(Dispatch).where(Dispatch.decision_id==decision_id,Dispatch.state=='PENDING'))).scalars():row.state='CANCELLED'
    await session.commit()
