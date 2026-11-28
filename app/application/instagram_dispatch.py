"""Individual Unified dispatch coordinator using durable production fences."""
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
    from app.application import instagram_fenced_worker as worker
    await session.rollback() # Worker commands own fresh transactions, release caller reads/locks.
    return await worker.run(did,provider=provider,grant_url_factory=grant_url_factory)

async def reconcile(session,did,*,provider):
    from app.application import instagram_fenced_worker as worker
    await session.rollback() # Worker commands own fresh transactions, release caller reads/locks.
    return await worker.reconcile(did,provider=provider)


async def resume_media(session,did,*,provider,runtime_enabled=False):
    if runtime_enabled is not True:raise ValueError('Live Instagram dispatch remains disabled')
    from app.application import instagram_fenced_worker as worker
    await session.rollback() # Worker commands own fresh transactions, release caller reads/locks.
    return await worker.resume(did,provider=provider)

async def interrupted(session,did,*,expected_updated_at,worker_confirmed_stopped=False):
    raise ValueError('Supervisor-attested recovery unavailable; no boolean override')
