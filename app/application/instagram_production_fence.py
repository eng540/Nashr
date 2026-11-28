"""Unregistered server-owned production linkage. CREATE-only safety candidate.

No runtime consumer. PUBLISH and media resume deliberately refuse until the
status-read/claim bridge and shared revoke path are implemented and reviewed.
"""
from sqlalchemy import select
from app.infrastructure.database.models import (
    InstagramProductionFenceModel as Link, InstagramIsolatedControlModel as Control,InstagramMediaGrantModel as Grant)
from app.application import instagram_write_authority as authority
from app.application import instagram_isolated_claims as claims
from app.application import instagram_publish_decisions as decisions
from app.application.instagram_plan_review import fingerprint


def pins(job, decision, grant):
    return fingerprint([str(job.id), decision.snapshot_hash, str(grant.id) if grant else None, grant.sha256 if grant else None])


async def claim_create(session, dispatch_id, *, grant_id, request_key, worker_id,
                       ownership_token):
    """Initialize legacy control and acquire CREATE in one owned transaction.

    No caller-provided generation, expiry, pins, decision IDs or booleans. A worker
    retains its own minted secret. The output is an internal claim receipt only.
    This transaction does not execute a provider or mark the legacy job claimed.
    """
    if session.in_transaction():
        raise ValueError('Fresh atomic production claim transaction required')
    async with session.begin():
        return await _claim_create_locked(session,dispatch_id,grant_id=grant_id,request_key=request_key,worker_id=worker_id,ownership_token=ownership_token)

async def _claim_create_locked(session,dispatch_id,*,grant_id,request_key,worker_id,ownership_token):
    # All commands on one production dispatch must use this stable advisory
    # fence, including future revoke/read/result paths. Not wired yet.
    from sqlalchemy import text
    key = int.from_bytes(dispatch_id.bytes[:8], 'big', signed=True)
    if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': key}):
        raise ValueError('Production dispatch fence busy')
    link = await session.scalar(select(Link).where(Link.dispatch_id == dispatch_id)
        .with_for_update(nowait=True).execution_options(populate_existing=True))
    control = None
    if link:
        control = await session.scalar(select(Control).where(Control.dispatch_id == dispatch_id)
            .with_for_update(nowait=True).execution_options(populate_existing=True))
        if not control:
            raise ValueError('Missing linked production control')
    else:
        # A synthetic control with a coincidental real dispatch ID is not
        # promoted into production. Only this verified transaction creates it.
        if await session.get(Control, dispatch_id):
            raise ValueError('Unowned preexisting control cannot become production')
    dispatch, job, decision, grant = await authority.validate_locked(
        session, dispatch_id, step='CREATE_CONTAINER', grant_id=grant_id)
    exact_pins = pins(job, decision, grant)
    generation = fingerprint(job.connection_binding)
    if not link:
        control = Control(dispatch_id=dispatch.id, generation=0, version=0,
            revoked=False, pins_hash=exact_pins, connection_generation=generation,
            decision_expires_at=decision.expires_at, grant_expires_at=grant.expires_at,
            grant_active=True)
        session.add(control)
        await session.flush()
        link = Link(dispatch_id=dispatch.id, execution_id=job.id,
            decision_id=decision.id, grant_id=grant.id, created_at=decisions.now())
        session.add(link)
        await session.flush()
    elif (link.execution_id != job.id or link.decision_id != decision.id
            or link.grant_id != grant.id or control.pins_hash != exact_pins
            or control.connection_generation != generation
            or control.decision_expires_at != decision.expires_at
            or control.grant_expires_at != grant.expires_at):
        raise ValueError('Exact authoritative production binding changed')
    return await claims.acquire_locked(session, dispatch.id, kind='WRITE',
        step='CREATE_CONTAINER', request_key=request_key, worker_id=worker_id,
        ownership_token=ownership_token, expected_generation=control.generation,
        expected_version=control.version, pins_hash=exact_pins,
        connection_generation=generation)


async def claim_publish(*args, **kwargs):
    raise ValueError('PUBLISH unavailable until status-read and shared revoke bridge is reviewed')


async def stop_dispatch(session, dispatch_id, *, request_key):
    """Unregistered individual Stop, server-resolved exact linked dispatch only.

    Not a batch Stop. Prior receipt retries keep their frozen scope and outcome
    history; no new control/child list is accepted from the caller.
    """
    if session.in_transaction():
        raise ValueError('Fresh atomic Stop transaction required')
    from sqlalchemy import text
    from app.infrastructure.database.models import (
        InstagramDispatchModel as Dispatch, InstagramExecutionModel as Job,
        InstagramPublishDecisionModel as Decision, InstagramMediaGrantModel as Grant,
        InstagramIsolatedStopModel as Stop)
    async with session.begin():
        key = int.from_bytes(dispatch_id.bytes[:8], 'big', signed=True)
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': key}):
            raise ValueError('Production dispatch fence busy')
        prior = await session.scalar(select(Stop).where(Stop.request_key == request_key))
        if prior:
            if (prior.scope.get('batch_id') != str(dispatch_id)
                    or [i['dispatch_id'] for i in prior.scope['items']] != [str(dispatch_id)]):
                raise ValueError('Stop key belongs to a different exact dispatch')
            return await claims.stop_receipt(session, prior)
        link = await session.scalar(select(Link).where(Link.dispatch_id == dispatch_id)
            .with_for_update(nowait=True))
        if not link:
            # Preclaim Stop initializes a terminal, grantless fence. It does not
            # validate a due/expiry window because revocation must still work.
            if await session.get(Control,dispatch_id):raise ValueError('Unowned synthetic control')
            dispatch=await authority._one(session,Dispatch,Dispatch.id==dispatch_id)
            job=await authority._one(session,Job,Job.id==dispatch.execution_id)
            decision=await authority._one(session,Decision,Decision.id==dispatch.decision_id)
            if (dispatch.state in {'RESULT_KNOWN','PUBLISHED','BLOCKED'} and job.state in {'PUBLISHED_ID_KNOWN','PUBLISHED'}
                    and job.media_id and decision.execution_id==job.id and job.connection_binding.get('login_mode')=='UNIFIED'):
                decision.state='REVOKED'
                for g in await session.scalars(select(Grant).where(Grant.execution_id==job.id).with_for_update(nowait=True)):g.state='REVOKED'
                return {'legacy_result':True,'outcome':'ALREADY_PUBLISHED','media_id':job.media_id,
                    'already_published_content_removed':False,'execution_enabled':False}
            if (dispatch.state!='PENDING' or job.state!='DRAFT' or job.container_id or job.media_id
                    or decision.execution_id!=job.id or job.connection_binding.get('login_mode')!='UNIFIED'
                    or fingerprint(decision.snapshot)!=decision.snapshot_hash):
                raise ValueError('Exact unclaimed individual dispatch required')
            existing=list((await session.scalars(select(Grant).where(Grant.execution_id==job.id).with_for_update(nowait=True))).all())
            if len(existing)>1 or any(g.decision_id!=decision.id for g in existing):raise ValueError('Ambiguous legacy grants')
            grant=existing[0] if existing else None
            control=Control(dispatch_id=dispatch.id,generation=0,version=0,revoked=False,
                pins_hash=pins(job,decision,grant),connection_generation=fingerprint(job.connection_binding),
                decision_expires_at=decision.expires_at,grant_expires_at=grant.expires_at if grant else decision.expires_at,
                grant_active=bool(grant and grant.state=='ACTIVE'))
            session.add(control);await session.flush()
            link=Link(dispatch_id=dispatch.id,execution_id=job.id,decision_id=decision.id,
                grant_id=grant.id if grant else None,created_at=decisions.now())
            session.add(link);await session.flush()
        control = await session.scalar(select(Control).where(Control.dispatch_id == dispatch_id)
            .with_for_update(nowait=True).execution_options(populate_existing=True))
        dispatch = await authority._one(session, Dispatch, Dispatch.id == dispatch_id)
        job = await authority._one(session, Job, Job.id == link.execution_id)
        decision = await authority._one(session, Decision, Decision.id == link.decision_id)
        grant = await authority._one(session, Grant, Grant.id == link.grant_id) if link.grant_id else None
        if (not control or dispatch.execution_id != job.id or dispatch.decision_id != decision.id
                or decision.execution_id != job.id or (grant and grant.execution_id != job.id)
                or (grant and grant.decision_id != decision.id) or pins(job, decision, grant) != control.pins_hash):
            raise ValueError('Production Stop ownership changed')
        result = await claims.stop_batch_locked(session, request_key=request_key,
            batch_id=dispatch.id, snapshot_hash=decision.snapshot_hash, action='STOP_ONE',
            items=[dict(dispatch_id=dispatch.id,generation=control.generation,version=control.version)])
        decision.state='REVOKED'
        if grant:grant.state='REVOKED'
        # In-flight writers keep their state and must report through owner CAS.
        if result['events'][0]['outcome']=='ACK_STOPPED_BEFORE_WRITE':
            dispatch.state='CANCELLED'
            if job.state=='DRAFT':job.state='CANCELLED'
        dispatch.updated_at=decisions.now()
        return result


async def finish_create(session, dispatch_id, *, claim_id, ownership_token,
                        worker_id, expected_claim_version, outcome, container_id=None):
    """Exact worker result CAS and real job result commit together, no network."""
    import re
    from sqlalchemy import text
    from app.infrastructure.database.models import InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job,InstagramIsolatedClaimModel as Claim
    if session.in_transaction():raise ValueError('Fresh atomic worker result transaction required')
    if outcome not in {'CONTAINER_KNOWN','UNKNOWN','DEFINITE_REJECTION','STOPPED_WITHOUT_WRITE'}:
        raise ValueError('Exact bounded CREATE result required')
    if (outcome=='CONTAINER_KNOWN') != bool(container_id):raise ValueError('Known CREATE requires exact container identity only')
    if container_id and not re.fullmatch(r'[0-9]{1,100}',container_id):raise ValueError('Invalid container identity')
    async with session.begin():
        key=int.from_bytes(dispatch_id.bytes[:8],'big',signed=True)
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':key}):raise ValueError('Production fence busy')
        link=await session.scalar(select(Link).where(Link.dispatch_id==dispatch_id).with_for_update(nowait=True))
        if not link:raise ValueError('Missing production linkage')
        control=await authority._one(session,Control,Control.dispatch_id==dispatch_id)
        claim=await authority._one(session,Claim,Claim.id==claim_id)
        dispatch=await authority._one(session,Dispatch,Dispatch.id==dispatch_id)
        job=await authority._one(session,Job,Job.id==link.execution_id)
        if (claim.dispatch_id!=dispatch_id or claim.write_step!='CREATE_CONTAINER'
                or dispatch.execution_id!=job.id or job.state!='DRAFT' or job.container_id or job.media_id):
            raise ValueError('Exact unconsumed CREATE result binding required')
        result=await claims.finish_locked(session,claim.id,ownership_token=ownership_token,
            worker_id=worker_id,expected_claim_version=expected_claim_version,outcome=outcome)
        if outcome=='CONTAINER_KNOWN':
            job.container_id=container_id;job.state='CONTAINER_CREATED'
            dispatch.state='BLOCKED' if control.revoked else 'WAITING_MEDIA'
        elif outcome=='UNKNOWN':job.state='CREATE_UNKNOWN';dispatch.state='RECONCILE_ONLY'
        elif outcome=='STOPPED_WITHOUT_WRITE':job.state='CANCELLED';dispatch.state='CANCELLED'
        else:job.state='FAILED';dispatch.state='BLOCKED'
        if outcome!='CONTAINER_KNOWN':
            grant=await authority._one(session,Grant,Grant.id==link.grant_id)
            grant.state='REVOKED';control.grant_active=False
        job.updated_at=dispatch.updated_at=decisions.now()
        return result


async def first_grant_and_claim(session,dispatch_id,*,request_key,worker_id,ownership_token):
    """One commit for first capability, exact production linkage and CREATE.

    The returned secret belongs only to this worker and is not recoverable.
    Existing grants/links cannot be renewed, adopted or replayed here.
    """
    from sqlalchemy import text
    from app.infrastructure.database.models import InstagramDispatchModel as Dispatch,InstagramMediaGrantModel as Grant
    from app.application import instagram_media_grants as grants
    if session.in_transaction():raise ValueError('Fresh first-grant transaction required')
    async with session.begin():
        key=int.from_bytes(dispatch_id.bytes[:8],'big',signed=True)
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':key}):raise ValueError('Production fence busy')
        if await session.get(Control,dispatch_id) or await session.get(Link,dispatch_id):raise ValueError('Already initialized')
        dispatch=await authority._one(session,Dispatch,Dispatch.id==dispatch_id)
        if dispatch.state!='PENDING':raise ValueError('Unclaimed pending dispatch required')
        if await session.scalar(select(Grant.id).where(Grant.execution_id==dispatch.execution_id)):
            raise ValueError('First grant only, never renew or adopt')
        grant,token=await grants.mint_locked(session,dispatch.execution_id,dispatch.decision_id)
        result=await _claim_create_locked(session,dispatch_id,grant_id=grant.id,request_key=request_key,worker_id=worker_id,ownership_token=ownership_token)
        from app.infrastructure.database.models import InstagramExecutionModel as Job
        j=await session.get(Job,dispatch.execution_id)
        result={**result,'grant_id':str(grant.id),'payload':dict(kind=j.kind,caption=j.caption,alt_text=j.alt_text,share_to_feed=j.share_to_feed)}
    return result,token
