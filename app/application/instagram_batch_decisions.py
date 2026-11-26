"""Dormant atomic Instagram batch coordinator, intentionally without HTTP routes.

Owns a fresh transaction. No provider calls, grants or byte exposure. Approval is
unreachable from the application until separately reviewed routes/UI are added.
Only already staged Unified execution drafts can enter this first batch shape.
"""
from datetime import datetime, timedelta
import re
from uuid import UUID
from sqlalchemy import select, text
from app.infrastructure.database.models import (
    InstagramBatchDraftModel as Batch, InstagramExecutionModel as Job,
    InstagramPublishDecisionModel as Decision, InstagramDispatchModel as Dispatch,
    ArtifactModel as Artifact, PlatformCopyModel as Copy,
    DistributionSelectionModel as Selection, InstagramConnectionModel as Connection,
    InstagramPlanDraftModel as Review)
from app.application import instagram_publish_decisions as decisions
from app.application import instagram_unified_execution as execution
from app.application.instagram_plan_review import fingerprint
from app.application.distribution_readiness import source_fingerprint, selection_version

MAX_ITEMS=20

def _fresh(session):
    if session.in_transaction():
        raise ValueError('Batch command requires a fresh transaction, never a partial caller transaction')

def _entries(entries):
    if not isinstance(entries,list) or not 1<=len(entries)<=MAX_ITEMS:
        raise ValueError('Select between one and twenty exact staged Instagram operations')
    parsed=[]
    for entry in entries:
        if set(entry)!={'execution_id','due_at','timezone'}:
            raise ValueError('Exact operation, UTC time and IANA zone required')
        due=entry['due_at']
        if not isinstance(due,datetime):raise ValueError('Explicit timezone-aware time required')
        from app.application.exact_schedule_time import timing
        when=timing(due,entry['timezone'],now=decisions.now())
        parsed.append(dict(execution_id=str(UUID(str(entry['execution_id']))),**when))
    if len({e['execution_id'] for e in parsed})!=len(parsed):raise ValueError('Duplicate operation')
    return parsed

async def _serialization(session):
    if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(606033)')):
        raise ValueError('Another batch is being reviewed or approved; reread before retrying')

async def _facts(session,entries,*,recheck_bytes=False):
    ids=[UUID(e['execution_id']) for e in entries]
    # NOWAIT fails the entire transaction rather than waiting through a lock-order
    # inversion with existing single-item handlers. No retry is hidden here.
    jobs=list((await session.execute(select(Job).where(Job.id.in_(ids)).order_by(Job.id)
        .with_for_update(nowait=True).execution_options(populate_existing=True))).scalars())
    if len(jobs)!=len(ids):raise ValueError('An exact execution draft is missing')
    by_id={str(j.id):j for j in jobs}
    material_ids=sorted({j.artifact_id for j in jobs},key=str)
    if len(material_ids)!=len(jobs):raise ValueError('Only one operation per original is allowed')
    artifacts=list((await session.execute(select(Artifact).where(Artifact.id.in_(material_ids))
        .order_by(Artifact.id).with_for_update(nowait=True).execution_options(populate_existing=True))).scalars())
    copies=list((await session.execute(select(Copy).where(Copy.artifact_id.in_(material_ids),Copy.platform=='instagram')
        .order_by(Copy.artifact_id).with_for_update(nowait=True).execution_options(populate_existing=True))).scalars())
    selections=list((await session.execute(select(Selection).where(Selection.artifact_id.in_(material_ids))
        .order_by(Selection.artifact_id).with_for_update(nowait=True).execution_options(populate_existing=True))).scalars())
    if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(606024)')):
        raise ValueError('Account lifecycle is changing; rereview later')
    if any(not isinstance(j.connection_binding,dict) or not j.connection_binding or j.connection_binding.get('login_mode')!='UNIFIED' or not j.connection_binding.get('review_id') for j in jobs):
        raise ValueError('Only explicitly bound Unified review drafts may enter a batch')
    try:review_ids=[UUID(j.connection_binding['review_id']) for j in jobs]
    except (ValueError,TypeError,AttributeError):raise ValueError('Invalid saved review binding') from None
    await session.execute(select(Review).where(Review.id.in_(review_ids)).order_by(Review.id).with_for_update(nowait=True).execution_options(populate_existing=True))
    await session.execute(select(Connection).where(Connection.id==1).with_for_update(nowait=True))
    a_by_id={a.id:a for a in artifacts};c_by_id={c.artifact_id:c for c in copies};s_by_id={s.artifact_id:s for s in selections}
    result=[]
    for entry in entries:
        job=by_id[entry['execution_id']];a=a_by_id.get(job.artifact_id);copy=c_by_id.get(job.artifact_id);choice=s_by_id.get(job.artifact_id)
        if job.state!='DRAFT' or (job.connection_binding or {}).get('login_mode')!='UNIFIED':
            raise ValueError('Only unclaimed Unified drafts may enter a batch')
        if not a or not copy or a.review_status!='APPROVED' or a.status!='AVAILABLE' or a.kind not in {'IMAGE','VIDEO'} or job.kind!=a.kind:
            raise ValueError('An original or its saved Instagram copy is unavailable')
        fp=source_fingerprint(a)
        if not choice or 'instagram' not in choice.platforms or choice.source_fingerprint!=fp:
            raise ValueError('A current saved Instagram destination choice is required per material')
        from app.application.central_platform_copies import evaluate
        if (job.source_fingerprint!=fp or copy.source_fingerprint!=fp or copy.version!=job.copy_version or
            copy.fields.get('description')!=job.caption or copy.fields.get('alt_text')!=job.alt_text or
            evaluate(a,copy)['field_status']!='FIELDS_VALIDATED'):
            raise ValueError('An original, copy or exact outgoing text changed')
        await execution.validate_binding(session,job)
        from app.application.instagram_media_pin import inspection_for_copy
        inspected=await inspection_for_copy(session,a.id,job.inspection_id,fingerprint=fp,copy_version=copy.version)
        if inspected.sha256!=job.media_sha256:raise ValueError('Inspected media differs from staged media')
        if recheck_bytes:
            from app.application.instagram_media_pin import recheck_pinned_bytes
            await recheck_pinned_bytes(session,job)
        existing=await session.scalar(select(Decision.id).where(Decision.execution_id==job.id))
        dispatched=await session.scalar(select(Dispatch.id).where(Dispatch.execution_id==job.id))
        conflict=await session.scalar(select(Job.id).where(Job.artifact_id==job.artifact_id,Job.id!=job.id,
            Job.account_id==job.account_id,Job.state!='CANCELLED').limit(1))
        if existing or dispatched or conflict:raise ValueError('Existing decision, result or unresolved operation requires separate review, never implicit replay')
        when=datetime.fromisoformat(entry['due_at'])
        from app.application.exact_schedule_time import timing
        timing(when,entry['timezone'],now=decisions.now())
        snapshot=decisions.snapshot(job,due_at=when,timezone_name=entry['timezone'])
        result.append(dict(execution_id=str(job.id),artifact_id=str(job.artifact_id),
            selection_version=selection_version(choice),selection_platforms=list(choice.platforms),
            inspection_id=str(job.inspection_id),snapshot=snapshot,decision_hash=fingerprint(snapshot)))
    return result

def describe(batch):
    return dict(id=str(batch.id),state=batch.state,snapshot_hash=batch.snapshot_hash,
        items=[{k:v for k,v in item.items() if k!='snapshot'}|{
            'account_id':item['snapshot']['account_id'],'username':item['snapshot']['username'],
            'kind':item['snapshot']['kind'],'caption':item['snapshot']['caption'],
            'alt_text':item['snapshot']['alt_text'],'share_to_feed':item['snapshot']['share_to_feed'],
            'due_at':item['snapshot']['due_at'],'timezone':item['snapshot']['timezone'],
            'local_time':item['snapshot']['local_time'],'media_sha256':item['snapshot']['media_sha256'],
            'audience':item['snapshot']['audience'],'media_disclosure':item['snapshot']['media_disclosure'],
            'disclosure_caveat':item['snapshot']['disclosure_caveat'],'copy_version':item['snapshot']['copy_version']}
            for item in batch.snapshot['items']],decision_ids=batch.decision_ids,
        execution_enabled=batch.state=='APPROVED',media_exposure_enabled=False,
        caveat='Dormant internal coordinator. No route can approve this batch. DRAFT is not a schedule or consent.')

async def stage(session,entries,*,request_key):
    _fresh(session)
    if not isinstance(request_key,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{8,100}',request_key):raise ValueError('A stable explicit idempotency key is required')
    parsed=_entries(entries);request_hash=fingerprint(parsed)
    async with session.begin():
        await _serialization(session)
        prior=await session.scalar(select(Batch).where(Batch.request_key==request_key).with_for_update(nowait=True))
        if prior:
            if prior.request_hash!=request_hash:raise ValueError('Idempotency key already names another exact request')
            return describe(prior)
        values=await _facts(session,parsed)
        snapshot=dict(platform='instagram',login_mode='UNIFIED',items=values)
        batch=Batch(request_key=request_key,request_hash=request_hash,snapshot=snapshot,
            snapshot_hash=fingerprint(snapshot),state='DRAFT',decision_ids=[],created_at=decisions.now())
        session.add(batch);await session.flush()
        return describe(batch)

async def approve(session,batch_id,*,snapshot_hash,evidence_ref,authenticated_owner=False,
                  exact_batch_approved=False,public_posts_approved=False,media_disclosures_approved=False):
    _fresh(session)
    if any(v is not True for v in [authenticated_owner,exact_batch_approved,public_posts_approved,media_disclosures_approved]):raise ValueError('Explicit exact batch, public posts and media disclosure approval required')
    if not isinstance(evidence_ref,str) or not re.fullmatch(r'(owner-session|trusted-message):[A-Za-z0-9_.:-]{8,240}',evidence_ref):raise ValueError('Authenticated approval source required')
    async with session.begin():
        await _serialization(session)
        batch=await session.scalar(select(Batch).where(Batch.id==batch_id).with_for_update(nowait=True))
        if not batch or batch.snapshot_hash!=snapshot_hash or fingerprint(batch.snapshot)!=snapshot_hash:raise ValueError('Batch snapshot changed or is missing')
        if batch.state=='APPROVED':return describe(batch)
        entries=[dict(execution_id=i['execution_id'],due_at=i['snapshot']['due_at'],timezone=i['snapshot']['timezone']) for i in batch.snapshot['items']]
        current=await _facts(session,entries,recheck_bytes=True)
        if current!=batch.snapshot['items']:raise ValueError('Batch content, account, selection, inspection or time changed; rereview the whole batch')
        for item in current:
            due=datetime.fromisoformat(item['snapshot']['due_at'])
            decision=Decision(execution_id=UUID(item['execution_id']),snapshot_hash=item['decision_hash'],
                snapshot=item['snapshot'],evidence_ref=evidence_ref,state='APPROVED',created_at=decisions.now(),expires_at=due+timedelta(minutes=15))
            session.add(decision);await session.flush()
            session.add(Dispatch(execution_id=decision.execution_id,decision_id=decision.id,due_at=due,state='PENDING',updated_at=decisions.now()))
            batch.decision_ids=[*batch.decision_ids,str(decision.id)]
        from app.application.exact_schedule_time import timing
        for item in current:
            timing(datetime.fromisoformat(item['snapshot']['due_at']),item['snapshot']['timezone'],now=decisions.now())
        batch.state='APPROVED';batch.evidence_ref=evidence_ref;batch.approved_at=decisions.now()
        await session.flush()
        return describe(batch)
