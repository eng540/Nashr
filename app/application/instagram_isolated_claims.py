"""Isolated protocol primitives. NO runtime, route, provider or provenance bridge.

Controls are synthetic protocol inputs, never authority to publish. No production
code creates them. Token is minted and retained by its caller, only a hash stored.
"""
import hashlib
import json
import secrets
from datetime import datetime,timezone,timedelta
from uuid import UUID
from sqlalchemy import select
from app.infrastructure.database.models import InstagramIsolatedControlModel as Control,InstagramIsolatedClaimModel as Claim,InstagramIsolatedStopModel as Stop,InstagramIsolatedStopEventModel as StopEvent

STEPS={'CREATE_CONTAINER','PUBLISH'}

def now():return datetime.now(timezone.utc)
def token():return secrets.token_urlsafe(32)
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def hash_value(value):return digest(json.dumps(value,sort_keys=True,default=str))
def fresh(s):
    if s.in_transaction():raise ValueError('Fresh owned transaction required')
def describe(row):
    return dict(id=str(row.id),dispatch_id=str(row.dispatch_id),kind=row.kind,step=row.write_step,
        state=row.state,version=row.version,generation=row.generation,control_version=row.control_version,
        result=row.result,execution_enabled=False)

async def locked(s,did):
    row=await s.scalar(select(Control).where(Control.dispatch_id==did).with_for_update(nowait=True).execution_options(populate_existing=True))
    if not row:raise ValueError('No isolated control')
    return row

async def acquire(s,did,**kw):
    fresh(s)
    async with s.begin():
        return await acquire_locked(s,did,**kw)

async def acquire_locked(s,did,*,kind,step,request_key,worker_id,ownership_token,expected_generation,expected_version,pins_hash,connection_generation):
    if not s.in_transaction():raise ValueError('Owned transaction required')
    if kind not in {'WRITE','READ'} or (kind=='WRITE' and step not in STEPS) or (kind=='READ' and step is not None):raise ValueError('Exact protocol step required')
    if not 8<=len(request_key)<=100 or not 1<=len(worker_id)<=100 or len(ownership_token)<40:raise ValueError('Stable key, worker identity and strong caller-minted token required')
    request_hash=hash_value([str(did),kind,step,worker_id,expected_generation,expected_version,pins_hash,connection_generation])
    c=await locked(s,did)
    prior=await s.scalar(select(Claim).where(Claim.request_key==request_key))
    if prior:
        if prior.request_hash!=request_hash or not secrets.compare_digest(prior.token_hash,digest(ownership_token)):raise ValueError('Key or ownership mismatch')
        return describe(prior)
    if c.generation!=expected_generation or c.version!=expected_version:raise ValueError('Stale control generation/version')
    if c.connection_generation!=connection_generation or c.pins_hash!=pins_hash:raise ValueError('Binding or content changed')
    active=await s.scalar(select(Claim.id).where(Claim.dispatch_id==did,Claim.kind=='WRITE',Claim.state=='ACTIVE'))
    if active:raise ValueError('An active write prevents overlapping write/read claims')
    if kind=='WRITE':
        if c.revoked or not c.grant_active or c.decision_expires_at<=now() or c.grant_expires_at<=now():raise ValueError('Decision or grant absent, expired or revoked')
        previous=await s.scalar(select(Claim.id).where(Claim.dispatch_id==did,Claim.write_step==step))
        if previous:raise ValueError('Step already claimed forever; a new exact operation is required')
        if step=='PUBLISH':
            create=await s.scalar(select(Claim).where(Claim.dispatch_id==did,Claim.write_step=='CREATE_CONTAINER'))
            if not create or create.state!='COMPLETED' or create.result.get('outcome')!='CONTAINER_KNOWN':raise ValueError('Known completed container required')
    else:
        if await s.scalar(select(Claim.id).where(Claim.dispatch_id==did,Claim.kind=='READ',Claim.state=='ACTIVE')):
            raise ValueError('An active read prevents overlapping reconciliation')
        if c.reconcile_after and c.reconcile_after>now():raise ValueError('Persisted read backoff has not elapsed')
    c.version+=1
    row=Claim(dispatch_id=did,request_key=request_key,request_hash=request_hash,token_hash=digest(ownership_token),
        kind=kind,write_step=step,state='ACTIVE',generation=c.generation,control_version=c.version,version=0,
        worker_id=worker_id,result={},created_at=now())
    s.add(row);await s.flush();return describe(row)

async def finish(s,claim_id,**kw):
    fresh(s)
    async with s.begin():
        return await finish_locked(s,claim_id,**kw)

async def finish_locked(s,claim_id,*,ownership_token,worker_id,expected_claim_version,outcome,retry_after_seconds=None):
    if not s.in_transaction():raise ValueError('Owned transaction required')
    allowed={'CONTAINER_KNOWN','PUBLISHED','DEFINITE_REJECTION','UNKNOWN','STOPPED_WITHOUT_WRITE','READ_CONFIRMED','READ_UNRESOLVED','READ_RATE_LIMITED'}
    if outcome not in allowed:raise ValueError('Bounded outcome required')
    if retry_after_seconds is not None and (type(retry_after_seconds) is not int or not 1<=retry_after_seconds<=86400):raise ValueError('Bounded provider backoff required')
    # Same control-first lock order as acquire/revoke; fetch identity only first.
    did=await s.scalar(select(Claim.dispatch_id).where(Claim.id==claim_id))
    if not did:raise ValueError('Missing claim')
    c=await locked(s,did)
    row=await s.scalar(select(Claim).where(Claim.id==claim_id).with_for_update(nowait=True).execution_options(populate_existing=True))
    if row.worker_id!=worker_id or not secrets.compare_digest(row.token_hash,digest(ownership_token)):raise ValueError('Exact claim ownership required')
    if row.version!=expected_claim_version or row.state!='ACTIVE':raise ValueError('Claim already resolved or changed')
    if row.kind=='READ':
        if not outcome.startswith('READ_'):raise ValueError('Read claim cannot report a write result')
        if row.control_version!=c.version or row.generation!=c.generation:
            row.state='SUPERSEDED';row.result={'outcome':'READ_SUPERSEDED'}
        else:
            row.state='COMPLETED';row.result={'outcome':outcome}
            c.reconcile_after=now()+timedelta(seconds=retry_after_seconds or 60)
    else:
        if outcome.startswith('READ_'):raise ValueError('Write claim cannot report a read result')
        if row.write_step=='CREATE_CONTAINER' and outcome=='PUBLISHED':raise ValueError('Create cannot assert publication')
        if row.write_step=='PUBLISH' and outcome=='CONTAINER_KNOWN':raise ValueError('Publish cannot assert container creation')
        row.state='UNKNOWN' if outcome=='UNKNOWN' else 'STOPPED_WITHOUT_WRITE' if outcome=='STOPPED_WITHOUT_WRITE' else 'COMPLETED'
        row.result={'outcome':outcome,'revoked_after_claim':c.generation!=row.generation or c.revoked}
    row.version+=1;c.version+=1
    if row.kind=='WRITE':
        initial=(await s.scalars(select(StopEvent).where(StopEvent.dispatch_id==did,StopEvent.claim_id==row.id,StopEvent.sequence==0))).all()
        for event in initial:
            # Claim CAS, under the same item lock, permits exactly one owner append.
            s.add(StopEvent(stop_id=event.stop_id,dispatch_id=did,claim_id=row.id,sequence=1,
                outcome=outcome,evidence={'claim_version':row.version,'control_version':c.version},created_at=now()))
    return describe(row)

async def revoke(s,did,*,expected_generation,expected_version):
    """Isolated single-control fence only, not a batch Stop implementation."""
    fresh(s)
    async with s.begin():
        c=await locked(s,did)
        if c.generation!=expected_generation or c.version!=expected_version:raise ValueError('Control changed')
        active=await s.scalar(select(Claim.id).where(Claim.dispatch_id==did,Claim.kind=='WRITE',Claim.state=='ACTIVE'))
        c.revoked=True;c.grant_active=False;c.generation+=1;c.version+=1
        return dict(dispatch_id=str(did),generation=c.generation,version=c.version,
            outcome='REQUESTED_IN_FLIGHT' if active else 'ACK_STOPPED_BEFORE_WRITE',execution_enabled=False)

async def recover(*args,**kwargs):
    # No attestation validator / authenticated audited recovery surface exists.
    # A boolean, quoted log line or callback claiming "verified" is not a substitute.
    raise ValueError('Recovery unavailable: exact supervisor attestation verification and authenticated audit flow are not implemented')


async def stop_batch(s,**kw):
    fresh(s)
    async with s.begin():
        return await stop_batch_locked(s,**kw)

async def stop_batch_locked(s,*,request_key,batch_id,snapshot_hash,action,items):
    """Synthetic exact scope only. No resolver or route exists for real children.

    Items carry expected generations/versions AND opaque control IDs. A future
    integration must supply server-resolved ownership, not accept client scope.
    This function is not registered anywhere and cannot stop production work.
    """
    if not s.in_transaction():raise ValueError('Owned transaction required')
    if action not in {'STOP_ONE','STOP_REMAINING'} or not 1<=len(items)<=20:raise ValueError('Bounded explicit stop action required')
    if action=='STOP_ONE' and len(items)!=1:raise ValueError('One exact item required')
    if not 8<=len(request_key)<=100 or len(snapshot_hash)!=64:raise ValueError('Exact request and snapshot required')
    ids=[str(UUID(str(i['dispatch_id']))) for i in items]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate scope')
    scope={'batch_id':str(UUID(str(batch_id))),'snapshot_hash':snapshot_hash,'action':action,
        'items':sorted([dict(dispatch_id=did,generation=i['generation'],version=i['version']) for did,i in zip(ids,items)],key=lambda i:i['dispatch_id'])}
    scope_hash=hash_value(scope)
    controls=[await locked(s,UUID(i['dispatch_id'])) for i in scope['items']]
    prior=await s.scalar(select(Stop).where(Stop.request_key==request_key))
    if prior:
        if prior.scope_hash!=scope_hash:raise ValueError('Request key scope changed')
        return await stop_receipt(s,prior)
    # All validation precedes the first revocation or receipt insert.
    for c,i in zip(controls,scope['items']):
        if c.generation!=i['generation'] or c.version!=i['version']:raise ValueError('Stale exact stop scope')
    request=Stop(request_key=request_key,scope_hash=scope_hash,scope=scope,created_at=now());s.add(request);await s.flush()
    for c in controls:
        claims=(await s.scalars(select(Claim).where(Claim.dispatch_id==c.dispatch_id,Claim.kind=='WRITE'))).all()
        active=next((r for r in claims if r.state=='ACTIVE'),None)
        published=any(r.result.get('outcome')=='PUBLISHED' for r in claims)
        unknown=any(r.state=='UNKNOWN' for r in claims)
        terminal=any(r.result.get('outcome') in {'DEFINITE_REJECTION','STOPPED_WITHOUT_WRITE'} for r in claims)
        outcome='ALREADY_PUBLISHED' if published else 'REQUESTED_IN_FLIGHT' if active else 'ALREADY_UNKNOWN' if unknown else 'ALREADY_TERMINAL' if terminal else 'ACK_STOPPED_BEFORE_WRITE'
        old_generation=c.generation;c.revoked=True;c.grant_active=False;c.generation+=1;c.version+=1
        s.add(StopEvent(stop_id=request.id,dispatch_id=c.dispatch_id,claim_id=active.id if active else None,
            sequence=0,outcome=outcome,evidence={'previous_generation':old_generation,'generation':c.generation,
                'control_version':c.version,'claim_version':active.version if active else None},created_at=now()))
    await s.flush();return await stop_receipt(s,request)

async def stop_receipt(s,request):
    events=(await s.scalars(select(StopEvent).where(StopEvent.stop_id==request.id).order_by(StopEvent.dispatch_id,StopEvent.sequence))).all()
    return {'id':str(request.id),'scope':request.scope,'events':[dict(dispatch_id=str(e.dispatch_id),sequence=e.sequence,outcome=e.outcome,evidence=e.evidence) for e in events],
        'execution_enabled':False}
