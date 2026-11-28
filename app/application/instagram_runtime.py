"""Bounded Unified publishing runtime. Only exact approved dispatches can run."""
import os
from urllib.parse import urlsplit
import httpx
from sqlalchemy import select,or_,and_
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job,InstagramPublishDecisionModel as Decision
from app.application import instagram_dispatch as dispatch,instagram_unified_execution as execution,instagram_publish_decisions as decisions


def public_origin():
    domain=os.getenv('RAILWAY_PUBLIC_DOMAIN','').strip()
    if not domain or '/' in domain or ':' in domain or not domain.endswith('.up.railway.app'):
        raise ValueError('Trusted public Railway origin required for exact media capability')
    return 'https://'+domain

async def process_approved():
    async with SessionFactory() as s:
        ids=list((await s.execute(select(Dispatch.id).where(or_(Dispatch.state.in_(['PENDING','WAITING_MEDIA','RESULT_KNOWN']),and_(Dispatch.state=='BLOCKED',Dispatch.execution_id.in_(select(Job.id).where(Job.state=='PUBLISHED_ID_KNOWN',Job.media_id.is_not(None))))),Dispatch.due_at<=decisions.now()).order_by(Dispatch.due_at).limit(5))).scalars())
    for did in ids:
        async with SessionFactory() as s:
            row=await s.get(Dispatch,did);job=await s.get(Job,row.execution_id)
            try:
                if not (job.state=='PUBLISHED_ID_KNOWN' and job.media_id):
                    decision=await s.get(Decision,row.decision_id,populate_existing=True)
                    if not decision or decision.state!='APPROVED' or decision.expires_at<=decisions.now():raise ValueError('Decision expired or revoked')
                    # Future decisions must not depend on a five-minute-old UI check.
                    await execution.refresh_due_binding(s,job)
                    await decisions.validate(s,job,row.decision_id)
                else:
                    # Confirmed ID recovery is read-only even after approval expiry.
                    await execution.refresh_due_binding(s,job)
                async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
                    provider=await execution.verified_provider(s,job,client)
                    if row.state=='PENDING':
                        await dispatch.run(s,did,provider=provider,grant_url_factory=lambda gid,token:public_origin()+'/instagram-media?capability='+token,runtime_enabled=True)
                    elif row.state=='WAITING_MEDIA':await dispatch.resume_media(s,did,provider=provider,runtime_enabled=True)
                    else:
                        # Known published IDs only need a read, never another publish.
                        if row.state=='BLOCKED':row.state='RESULT_KNOWN';await s.commit()
                        await dispatch.reconcile(s,did,provider=provider)
            except Exception:
                # Claims, not scheduler error handlers, own durable outcomes.
                # Backoff/contention/Stop must never overwrite an active writer
                # or turn a transient status read into a new publishing attempt.
                await s.rollback()
