"""Revocable, short-lived exact-byte capabilities. No HTTP route is registered.

Mint and read are internal mechanics only. A future runtime must explicitly
activate a reviewed bearer endpoint; nothing here exposes stored media today.
"""
import hashlib,secrets
from datetime import datetime,timedelta
from sqlalchemy import select
from app.infrastructure.database.models import InstagramMediaGrantModel as Grant,InstagramExecutionModel as Job,ArtifactModel,PlatformCopyModel,PlatformCopyMediaModel
from app.application import instagram_publish_decisions as decisions
from app.application.instagram_media_pin import recheck_pinned_bytes
from app.infrastructure.artifact_storage import S3ArtifactStorage


def digest(token):return hashlib.sha256(token.encode()).hexdigest()

async def mint(session,jid,decision_id,*,token_seconds=900):
    if type(token_seconds) is not int or not 1<=token_seconds<=900:raise ValueError('Grant lifetime must be at most fifteen minutes')
    job=(await session.execute(select(Job).where(Job.id==jid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not job or job.state!='DRAFT':raise ValueError('Unclaimed execution required')
    decision=await decisions.validate(session,job,decision_id)
    if decisions.now()<datetime.fromisoformat(decision.snapshot['due_at']):raise ValueError('Do not expose media before the approved publication time')
    await recheck_pinned_bytes(session,job)
    old=(await session.execute(select(Grant).where(Grant.execution_id==jid,Grant.state=='ACTIVE'))).scalars().first()
    if old:raise ValueError('Revoke existing media grant before minting another')
    # Recheck after private inspection, before minting the capability.
    await decisions.validate(session,job,decision_id)
    token=secrets.token_urlsafe(32)
    row=Grant(execution_id=jid,decision_id=decision_id,capability_hash=digest(token),sha256=job.media_sha256,state='ACTIVE',reads=0,created_at=decisions.now(),expires_at=min(decision.expires_at,decisions.now()+timedelta(seconds=token_seconds)))
    session.add(row);await session.commit();return row,token

async def mint_locked(session,jid,decision_id,*,token_seconds=900):
    """Caller-owned transaction only, never exposes a token before commit."""
    from sqlalchemy.orm import SessionTransactionOrigin
    tx=session.sync_session.get_transaction()
    if not tx or tx.origin is not SessionTransactionOrigin.BEGIN:
        raise ValueError("Owned grant transaction required")
    if type(token_seconds) is not int or not 1<=token_seconds<=900:raise ValueError("Bounded grant lifetime required")
    job=(await session.execute(select(Job).where(Job.id==jid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not job or job.state!='DRAFT':raise ValueError('Unclaimed execution required')
    decision=await decisions.validate(session,job,decision_id)
    if decisions.now()<datetime.fromisoformat(decision.snapshot['due_at']):raise ValueError('Do not expose media before the approved publication time')
    await recheck_pinned_bytes(session,job)
    old=(await session.execute(select(Grant).where(Grant.execution_id==jid,Grant.state=='ACTIVE'))).scalars().first()
    if old:raise ValueError('Revoke existing media grant before minting another')
    # Recheck after private inspection, before minting the capability.
    await decisions.validate(session,job,decision_id)
    token=secrets.token_urlsafe(32)
    row=Grant(execution_id=jid,decision_id=decision_id,capability_hash=digest(token),sha256=job.media_sha256,state='ACTIVE',reads=0,created_at=decisions.now(),expires_at=min(decision.expires_at,decisions.now()+timedelta(seconds=token_seconds)))
    session.add(row);await session.flush();return row,token

async def read(session,token):
    if not isinstance(token,str) or len(token)!=43:raise ValueError('Media grant unavailable')
    # Identity lookup only before entering the shared dispatch fence. No row lock
    # in the opposite grant->control order can race Stop/first-claim.
    identity=await session.scalar(select(Grant.execution_id).where(Grant.capability_hash==digest(token)))
    from app.infrastructure.database.models import InstagramDispatchModel as Dispatch
    did=await session.scalar(select(Dispatch.id).where(Dispatch.execution_id==identity)) if identity else None
    await session.rollback()
    if not did:raise ValueError('Media grant unavailable')
    from app.application import instagram_fenced_media_status as media
    async with session.begin():
        link,control,dispatch,job=await media.lock(session,did)
        grant=await session.scalar(select(Grant).where(Grant.id==link.grant_id).with_for_update(nowait=True).execution_options(populate_existing=True))
        if (not grant or grant.capability_hash!=digest(token) or control.revoked or not control.grant_active
                or grant.state!='ACTIVE' or grant.expires_at<=decisions.now() or grant.reads>=20
                or job.state in {'CANCELLED','FAILED','PUBLISHED'}):raise ValueError('Media grant unavailable')
        from app.application import instagram_write_authority as authority
        await authority.validate_locked(session,did,step='CREATE_CONTAINER' if job.state=='DRAFT' else 'PUBLISH',grant_id=grant.id)
        original=await session.get(ArtifactModel,job.artifact_id);copy=await session.get(PlatformCopyModel,(job.artifact_id,'instagram'))
        asset=await session.get(PlatformCopyMediaModel,copy.selected_media_id) if copy.selected_media_id else original
        content=await S3ArtifactStorage.from_environment().get_bytes(asset.storage_uri,max_bytes=300_000_000)
        if hashlib.sha256(content).hexdigest()!=grant.sha256:raise ValueError('Pinned bytes changed')
        await decisions.validate(session,job,grant.decision_id)
        await recheck_pinned_bytes(session,job)
        if grant.expires_at<=decisions.now():raise ValueError('Media grant expired during read')
        grant.reads+=1
        mime=asset.mime_type
    return content,mime

async def revoke(session,gid):
    row=await session.get(Grant,gid)
    if not row:raise ValueError('Media grant unavailable')
    return await decisions.revoke(session,row.decision_id)
