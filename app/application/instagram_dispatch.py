"""Dormant Unified dispatch coordinator. No production scheduler registration.

A future runtime owns secure capability URLs and an independently reviewed
activation gate. The default gate blocks before provider or storage access.
"""
from datetime import datetime
from sqlalchemy import select
from app.infrastructure.database.models import InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job
from app.application import instagram_publish_decisions as decisions,instagram_execution as core,instagram_media_grants as grants

async def schedule(session,jid,decision_id):
    job=(await session.execute(select(Job).where(Job.id==jid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not job or job.state!='DRAFT':raise ValueError('Unclaimed execution draft required')
    decision=await decisions.validate(session,job,decision_id)
    due=datetime.fromisoformat(decision.snapshot['due_at'])
    if due<=decisions.now():raise ValueError('Approved due time elapsed; request a new exact decision')
    existing=(await session.execute(select(Dispatch).where(Dispatch.execution_id==jid))).scalar_one_or_none()
    if existing:
        if existing.decision_id!=decision_id or existing.state!='PENDING':raise ValueError('Dispatch already claimed or cancelled')
        return existing
    row=Dispatch(execution_id=jid,decision_id=decision_id,due_at=due,state='PENDING',updated_at=decisions.now());session.add(row);await session.commit();return row

async def due_ids(session,*,limit=20):
    if type(limit) is not int or not 1<=limit<=20:raise ValueError('Bounded dispatch scan required')
    return list((await session.execute(select(Dispatch.id).where(Dispatch.state=='PENDING',Dispatch.due_at<=decisions.now()).order_by(Dispatch.due_at).limit(limit))).scalars())

async def run(session,did,*,provider,grant_url_factory,runtime_enabled=False):
    if runtime_enabled is not True:raise ValueError('Live Instagram dispatch remains disabled')
    row=(await session.execute(select(Dispatch).where(Dispatch.id==did).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not row or row.state!='PENDING' or row.due_at>decisions.now():raise ValueError('Dispatch absent, not due or already claimed')
    job=await session.get(Job,row.execution_id,populate_existing=True)
    await decisions.validate(session,job,row.decision_id)
    await core.validate_provider_binding(session,job,provider)
    if provider.account_id!=job.account_id:raise ValueError('Verified pinned provider required')
    row.state='CLAIMED';row.updated_at=decisions.now();await session.commit()
    grant=None
    try:
        grant,token=await grants.mint(session,job.id,row.decision_id)
        # Future capability URL factory must never persist or log the token/URL.
        url=grant_url_factory(grant.id,token)
        await decisions.validate(session,job,row.decision_id)
        job=await core.create_container(session,job.id,provider=provider,media_url=url,media_sha256=job.media_sha256,authorized=True,public_publish_authorized=True,media_disclosure_authorized=True)
        if job.state=='CONTAINER_CREATED':
            await decisions.validate(session,job,row.decision_id)
            job=await core.publish(session,job.id,provider=provider,media_sha256=job.media_sha256,authorized=True,public_publish_authorized=True)
        row.state='WAITING_MEDIA' if job.state=='WAITING_MEDIA' else 'RESULT_KNOWN' if job.state=='PUBLISHED_ID_KNOWN' else 'RECONCILE_ONLY' if 'UNKNOWN' in job.state else 'BLOCKED'
    except Exception:
        # No automatic replay after any claimed attempt or lost response.
        row.state='RECONCILE_ONLY'
    finally:
        # Meta may fetch bytes asynchronously after container creation. Keep
        # only a bounded grant for WAITING_MEDIA; expiry/revocation still wins.
        if grant and row.state!='WAITING_MEDIA':await grants.revoke(session,grant.id)
        row.updated_at=decisions.now();await session.commit()
    return row

async def reconcile(session,did,*,provider):
    row=(await session.execute(select(Dispatch).where(Dispatch.id==did).with_for_update())).scalar_one_or_none()
    if not row or row.state not in {'RESULT_KNOWN','RECONCILE_ONLY','WAITING_MEDIA'}:raise ValueError('No inactive result to reconcile')
    job=await core.reconcile(session,row.execution_id,provider=provider)
    if job.state=='PUBLISHED':row.state='PUBLISHED'
    elif job.state=='FAILED':row.state='BLOCKED'
    row.updated_at=decisions.now();await session.commit();return row


async def resume_media(session,did,*,provider,runtime_enabled=False):
    if runtime_enabled is not True:raise ValueError('Live Instagram dispatch remains disabled')
    row=(await session.execute(select(Dispatch).where(Dispatch.id==did).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not row or row.state!='WAITING_MEDIA':raise ValueError('No resumable media status read')
    job=await session.get(Job,row.execution_id,populate_existing=True)
    await decisions.validate(session,job,row.decision_id)
    row.state='CLAIMED';row.updated_at=decisions.now();await session.commit()
    try:
        job=await core.publish(session,job.id,provider=provider,media_sha256=job.media_sha256,authorized=True,public_publish_authorized=True)
        row.state='WAITING_MEDIA' if job.state=='WAITING_MEDIA' else 'RESULT_KNOWN' if job.state=='PUBLISHED_ID_KNOWN' else 'RECONCILE_ONLY' if 'UNKNOWN' in job.state else 'BLOCKED'
    except Exception:row.state='RECONCILE_ONLY'
    if row.state!='WAITING_MEDIA':
        from app.infrastructure.database.models import InstagramMediaGrantModel as Grant
        for grant in (await session.execute(select(Grant).where(Grant.execution_id==job.id,Grant.state=='ACTIVE'))).scalars():grant.state='REVOKED'
    row.updated_at=decisions.now();await session.commit();return row

async def interrupted(session,did,*,expected_updated_at,worker_confirmed_stopped=False):
    if worker_confirmed_stopped is not True:raise ValueError('Worker stopped must be established; no age-based retry')
    row=(await session.execute(select(Dispatch).where(Dispatch.id==did).with_for_update())).scalar_one_or_none()
    if not row or row.state!='CLAIMED' or row.updated_at!=expected_updated_at:raise ValueError('Dispatch claim changed')
    row.state='RECONCILE_ONLY';row.updated_at=decisions.now();await session.commit();return row
