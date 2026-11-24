"""Bounded Unified publishing runtime. Only exact approved dispatches can run."""
import os
from urllib.parse import urlsplit
import httpx
from sqlalchemy import select
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job
from app.application import instagram_dispatch as dispatch,instagram_unified_execution as execution,instagram_publish_decisions as decisions


def public_origin():
    domain=os.getenv('RAILWAY_PUBLIC_DOMAIN','').strip()
    if not domain or '/' in domain or ':' in domain or not domain.endswith('.up.railway.app'):
        raise ValueError('Trusted public Railway origin required for exact media capability')
    return 'https://'+domain

async def process_approved():
    async with SessionFactory() as s:
        ids=list((await s.execute(select(Dispatch.id).where(Dispatch.state.in_(['PENDING','WAITING_MEDIA','RESULT_KNOWN']),Dispatch.due_at<=decisions.now()).order_by(Dispatch.due_at).limit(5))).scalars())
    for did in ids:
        async with SessionFactory() as s:
            row=await s.get(Dispatch,did);job=await s.get(Job,row.execution_id)
            try:
                await decisions.validate(s,job,row.decision_id)
                async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
                    provider=await execution.verified_provider(s,job,client)
                    if row.state=='PENDING':
                        await dispatch.run(s,did,provider=provider,grant_url_factory=lambda gid,token:public_origin()+'/instagram-media?capability='+token,runtime_enabled=True)
                    elif row.state=='WAITING_MEDIA':await dispatch.resume_media(s,did,provider=provider,runtime_enabled=True)
                    else:await dispatch.reconcile(s,did,provider=provider)
            except Exception:
                # Never retry a provider mutation from an uncertain claim.
                await s.rollback();row=await s.get(Dispatch,did,populate_existing=True)
                if row and row.state in {'PENDING','WAITING_MEDIA','RESULT_KNOWN'}:
                    row.state='BLOCKED';row.updated_at=decisions.now();await s.commit()
