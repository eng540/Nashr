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

async def read(session,token):
    if not isinstance(token,str) or len(token)!=43:raise ValueError('Media grant unavailable')
    grant=(await session.execute(select(Grant).where(Grant.capability_hash==digest(token)).with_for_update())).scalar_one_or_none()
    if not grant or grant.state!='ACTIVE' or grant.expires_at<=decisions.now() or grant.reads>=20:raise ValueError('Media grant unavailable')
    job=await session.get(Job,grant.execution_id,populate_existing=True)
    if not job or job.state in {'CANCELLED','FAILED','PUBLISHED'}:raise ValueError('Media grant unavailable')
    await decisions.validate(session,job,grant.decision_id)
    await recheck_pinned_bytes(session,job)
    original=await session.get(ArtifactModel,job.artifact_id);copy=await session.get(PlatformCopyModel,(job.artifact_id,'instagram'))
    asset=await session.get(PlatformCopyMediaModel,copy.selected_media_id) if copy.selected_media_id else original
    content=await S3ArtifactStorage.from_environment().get_bytes(asset.storage_uri,max_bytes=300_000_000)
    if hashlib.sha256(content).hexdigest()!=grant.sha256:raise ValueError('Pinned bytes changed')
    # Re-read authority and source after the potentially slow private read.
    await session.refresh(grant)
    if grant.state!='ACTIVE':raise ValueError('Media grant revoked during read')
    await decisions.validate(session,job,grant.decision_id)
    await recheck_pinned_bytes(session,job)
    if grant.expires_at<=decisions.now():raise ValueError('Media grant expired during read')
    grant.reads+=1;await session.commit()
    return content,asset.mime_type

async def revoke(session,gid):
    row=await session.get(Grant,gid)
    if row:row.state='REVOKED';await session.commit()
