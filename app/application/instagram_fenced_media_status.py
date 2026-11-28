"""Unregistered status-read and PUBLISH claim bridge, no provider caller.

READ observations are private bounded evidence. No status supplied by an HTTP
client or synthetic callback is accepted as a production action. Only a future
trusted worker retains its claim secret and submits its provider read result.
"""
from datetime import timedelta
from sqlalchemy import select,text
from app.infrastructure.database.models import (
    InstagramProductionFenceModel as Link,InstagramIsolatedControlModel as Control,
    InstagramIsolatedClaimModel as Claim,InstagramProductionReadModel as Observation,
    InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job,
    InstagramPublishDecisionModel as Decision,InstagramMediaGrantModel as Grant)
from app.application import instagram_production_fence as fence
from app.application import instagram_isolated_claims as claims
from app.application import instagram_write_authority as authority
from app.application import instagram_publish_decisions as decisions
from app.application import instagram_unified_execution as unified
from app.application.instagram_plan_review import fingerprint


async def lock(session,did):
    key=int.from_bytes(did.bytes[:8],'big',signed=True)
    if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':key}):raise ValueError('Production fence busy')
    link=await authority._one(session,Link,Link.dispatch_id==did)
    control=await authority._one(session,Control,Control.dispatch_id==did)
    dispatch=await authority._one(session,Dispatch,Dispatch.id==did)
    job=await authority._one(session,Job,Job.id==link.execution_id)
    if dispatch.execution_id!=job.id or dispatch.decision_id!=link.decision_id:raise ValueError('Exact production linkage changed')
    return link,control,dispatch,job


async def claim_status(session,did,*,request_key,worker_id,ownership_token):
    if session.in_transaction():raise ValueError('Fresh status claim transaction required')
    async with session.begin():
        link,c,d,j=await lock(session,did)
        if not j.container_id or j.state in {'CREATING','PUBLISHING'}:raise ValueError('Known inactive container required')
        # Read-only reconciliation remains available after revocation/expiry,
        # but cannot switch accounts or accept a reconnected binding.
        await unified.validate_binding(session,j)
        if fingerprint(j.connection_binding)!=c.connection_generation:raise ValueError('Read connection changed')
        result=await claims.acquire_locked(session,did,kind='READ',step=None,
            request_key=request_key,worker_id=worker_id,ownership_token=ownership_token,
            expected_generation=c.generation,expected_version=c.version,
            pins_hash=c.pins_hash,connection_generation=c.connection_generation)
        return {**result,'container_id':j.container_id,'media_id':j.media_id}


async def finish_status(session,did,*,claim_id,worker_id,ownership_token,
                        expected_claim_version,status,retry_after_seconds=60):
    if session.in_transaction():raise ValueError('Fresh status result transaction required')
    if status not in {'IN_PROGRESS','FINISHED','PUBLISHED','ERROR','EXPIRED','READ_FAILED','RATE_LIMITED'}:raise ValueError('Bounded provider status required')
    async with session.begin():
        link,c,d,j=await lock(session,did)
        claim=await authority._one(session,Claim,Claim.id==claim_id)
        if claim.dispatch_id!=did or claim.kind!='READ':raise ValueError('Exact read claim required')
        outcome='READ_RATE_LIMITED' if status=='RATE_LIMITED' else 'READ_UNRESOLVED' if status=='READ_FAILED' else 'READ_CONFIRMED'
        result=await claims.finish_locked(session,claim.id,ownership_token=ownership_token,
            worker_id=worker_id,expected_claim_version=expected_claim_version,
            outcome=outcome,retry_after_seconds=retry_after_seconds)
        if result['state']=='COMPLETED':
            session.add(Observation(claim_id=claim.id,dispatch_id=did,control_version=c.version,
                container_id=j.container_id,status=status,created_at=decisions.now()))
            if status=='PUBLISHED' and not j.media_id:
                j.state='PUBLISHED_ID_UNKNOWN';d.state='RECONCILE_ONLY'
            elif status in {'ERROR','EXPIRED'} and not j.media_id:
                j.state='FAILED';d.state='BLOCKED'
            j.updated_at=d.updated_at=decisions.now()
        return result


async def claim_publish(session,did,*,status_claim_id,request_key,worker_id,ownership_token):
    if session.in_transaction():raise ValueError('Fresh PUBLISH claim transaction required')
    async with session.begin():
        link,c,d,j=await lock(session,did)
        observed=await authority._one(session,Observation,Observation.claim_id==status_claim_id)
        if (observed.dispatch_id!=did or observed.status!='FINISHED'
                or observed.container_id!=j.container_id or observed.control_version!=c.version
                or observed.created_at>decisions.now()
                or observed.created_at<decisions.now()-timedelta(seconds=60)):
            raise ValueError('Fresh exact FINISHED observation at unchanged fence required')
        dispatch,job,decision,grant=await authority.validate_locked(session,did,step='PUBLISH',grant_id=link.grant_id)
        if (fence.pins(job,decision,grant)!=c.pins_hash
                or fingerprint(job.connection_binding)!=c.connection_generation
                or c.decision_expires_at!=decision.expires_at or c.grant_expires_at!=grant.expires_at):
            raise ValueError('Production authority binding changed')
        # Full locked authority/byte reread above may be slow; status freshness is
        # bounded again here. Stop changes generation/version under same fence.
        if observed.created_at<decisions.now()-timedelta(seconds=60):raise ValueError('Readiness observation elapsed during private byte checks')
        result=await claims.acquire_locked(session,did,kind='WRITE',step='PUBLISH',
            request_key=request_key,worker_id=worker_id,ownership_token=ownership_token,
            expected_generation=c.generation,expected_version=c.version,
            pins_hash=c.pins_hash,connection_generation=c.connection_generation)
        return {**result,'container_id':j.container_id}


async def finish_publish(session,did,*,claim_id,worker_id,ownership_token,
                         expected_claim_version,outcome,media_id=None):
    import re
    if session.in_transaction():raise ValueError('Fresh PUBLISH result transaction required')
    if outcome not in {'PUBLISHED','UNKNOWN','DEFINITE_REJECTION','STOPPED_WITHOUT_WRITE'}:raise ValueError('Bounded publish outcome required')
    if (outcome=='PUBLISHED')!=bool(media_id):raise ValueError('Exact known published media identity required')
    if media_id and not re.fullmatch(r'[0-9]{1,100}',media_id):raise ValueError('Invalid media identity')
    async with session.begin():
        link,c,d,j=await lock(session,did)
        claim=await authority._one(session,Claim,Claim.id==claim_id)
        if (claim.dispatch_id!=did or claim.kind!='WRITE' or claim.write_step!='PUBLISH'
                or j.state not in {'WAITING_MEDIA','CONTAINER_CREATED'} or not j.container_id or j.media_id):raise ValueError('Exact unconsumed publish claim required')
        result=await claims.finish_locked(session,claim.id,worker_id=worker_id,
            ownership_token=ownership_token,expected_claim_version=expected_claim_version,outcome=outcome)
        if outcome=='PUBLISHED':j.media_id=media_id;j.state='PUBLISHED_ID_KNOWN';d.state='RESULT_KNOWN'
        elif outcome=='UNKNOWN':j.state='PUBLISH_UNKNOWN';d.state='RECONCILE_ONLY'
        elif outcome=='STOPPED_WITHOUT_WRITE':j.state='CANCELLED';d.state='CANCELLED'
        else:j.state='FAILED';d.state='BLOCKED'
        grant=await authority._one(session,Grant,Grant.id==link.grant_id);grant.state='REVOKED'
        j.updated_at=d.updated_at=decisions.now()
        return result


async def finish_permalink(session,did,*,claim_id,worker_id,ownership_token,
                           expected_claim_version,media_id,permalink):
    from urllib.parse import urlsplit
    import re
    u=urlsplit(permalink if isinstance(permalink,str) else '')
    if (not re.fullmatch(r'[0-9]{1,100}',media_id) or len(permalink)>2048
            or u.scheme!='https' or u.hostname not in {'instagram.com','www.instagram.com'}
            or u.username or u.password or not u.path.startswith(('/p/','/reel/','/tv/'))):
        raise ValueError('Bounded verified Instagram permalink required')
    if session.in_transaction():raise ValueError('Fresh permalink result transaction required')
    async with session.begin():
        link,c,d,j=await lock(session,did)
        claim=await authority._one(session,Claim,Claim.id==claim_id)
        if claim.dispatch_id!=did or claim.kind!='READ' or j.media_id!=media_id:raise ValueError('Exact result READ binding required')
        result=await claims.finish_locked(session,claim.id,ownership_token=ownership_token,
            worker_id=worker_id,expected_claim_version=expected_claim_version,outcome='READ_CONFIRMED')
        if result['state']=='COMPLETED':
            j.permalink=permalink;j.state='PUBLISHED';d.state='PUBLISHED'
            j.updated_at=d.updated_at=decisions.now()
        return result
