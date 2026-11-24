"""Durable synthetic-provider execution core, not wired into production routes.

Production remains unavailable until account lifecycle, explicit publish approval,
media grants, measured readiness and scheduler integration are accepted together.
No preview calls this module; it never makes media publicly readable itself.
"""
from datetime import datetime,timezone
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,InstagramExecutionModel as Job
from app.application.distribution_readiness import source_fingerprint
from app.adapters.publishing.instagram import InstagramProviderError,ID


def now():return datetime.now(timezone.utc)
def runtime_status():
    return {'programming_state':'SYNTHETIC_PROVIDER_CORE','live_account_state':'NOT_VERIFIED','external_acceptance':'NOT_RUN','execution_enabled':False,'media_exposure_enabled':False}

async def prepare(session,uid,*,account_id,media_sha256,copy_version,fingerprint,inspection_id=None,share_to_feed=None,connection_binding=None):
    import re
    if not ID.fullmatch(account_id) or not re.fullmatch(r'[a-f0-9]{64}',media_sha256):raise ValueError('Invalid pinned account or media digest')
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())).scalar_one_or_none()
    copy=await session.get(PlatformCopyModel,(uid,'instagram'))
    if row is None or copy is None or row.review_status!='APPROVED' or row.status!='AVAILABLE' or row.kind not in {'IMAGE','VIDEO'}:raise ValueError('Approved original image or video required')
    if source_fingerprint(row)!=fingerprint or copy.source_fingerprint!=fingerprint or copy.version!=copy_version:raise ValueError('Source or copy changed')
    if row.kind=='VIDEO' and not isinstance(share_to_feed,bool):raise ValueError('Explicit Reel feed choice required')
    from app.application.central_platform_copies import evaluate
    if evaluate(row,copy)['field_status']!='FIELDS_VALIDATED':raise ValueError('Instagram fields are blocked')
    from app.application.instagram_media_pin import inspection_for_copy
    if inspection_id is None:raise ValueError('Saved selected-media inspection required')
    evidence=await inspection_for_copy(session,uid,inspection_id,fingerprint=fingerprint,copy_version=copy_version)
    if evidence.sha256!=media_sha256:raise ValueError('Inspected digest differs')
    if evaluate(row,copy)['field_status']!='FIELDS_VALIDATED':raise ValueError('Instagram fields are blocked')
    job=Job(connection_binding=connection_binding or {},inspection_id=inspection_id,artifact_id=uid,account_id=account_id,source_fingerprint=fingerprint,copy_version=copy_version,media_sha256=media_sha256,kind=row.kind,caption=copy.fields['description'],alt_text=copy.fields['alt_text'],share_to_feed=share_to_feed,state='DRAFT',created_at=now(),updated_at=now())
    session.add(job);await session.commit();return job

async def _locked(session,job_id):
    job=(await session.execute(select(Job).where(Job.id==job_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if job is None:raise ValueError('Execution record not found')
    return job

async def _valid(session,job,provider,media_sha256):
    if job.connection_binding:
        await validate_provider_binding(session,job,provider)
    if provider.account_id!=job.account_id or media_sha256!=job.media_sha256:raise ValueError('Pinned account or media changed')
    from app.application.instagram_media_pin import recheck_pinned_bytes
    await recheck_pinned_bytes(session,job)
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==job.artifact_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    copy=await session.get(PlatformCopyModel,(job.artifact_id,'instagram'),populate_existing=True)
    if row is None or copy is None or row.review_status!='APPROVED' or row.status!='AVAILABLE' or source_fingerprint(row)!=job.source_fingerprint or copy.source_fingerprint!=job.source_fingerprint or copy.version!=job.copy_version:raise ValueError('Original or platform copy changed; no execution')
    from app.application.central_platform_copies import evaluate
    if evaluate(row,copy)['field_status']!='FIELDS_VALIDATED' or copy.fields.get('description')!=job.caption or copy.fields.get('alt_text')!=job.alt_text:raise ValueError('Pinned outgoing fields changed or are blocked')

async def create_container(session,job_id,*,provider,media_url,media_sha256,authorized=False,media_disclosure_authorized=False,public_publish_authorized=False):
    if authorized is not True:raise ValueError('Explicit publishing authority required; preview does not authorize media access')
    job=await _locked(session,job_id)
    if job.connection_binding and (media_disclosure_authorized is not True or public_publish_authorized is not True):raise ValueError('Explicit public publication and provider media disclosure authority required')
    if job.state!='DRAFT':raise ValueError('Container creation already attempted; never repeat unknown outcomes')
    await _valid(session,job,provider,media_sha256)
    job.state='CREATING';job.updated_at=now();await session.commit()
    try:container=await provider.create_container(kind=job.kind,media_url=media_url,caption=job.caption,alt_text=job.alt_text,share_to_feed=job.share_to_feed)
    except InstagramProviderError as exc:
        job.state='CREATE_UNKNOWN' if exc.outcome_unknown else 'FAILED';job.error_code=exc.code;job.updated_at=now();await session.commit();return job
    except Exception:
        job.state='CREATE_UNKNOWN';job.error_code='INSTAGRAM_OUTCOME_UNKNOWN';job.updated_at=now();await session.commit();return job
    job.container_id=container;job.state='CONTAINER_CREATED';job.updated_at=now();await session.commit();return job

async def publish(session,job_id,*,provider,media_sha256,authorized=False,public_publish_authorized=False):
    if authorized is not True:raise ValueError('Explicit publishing authority required')
    job=await _locked(session,job_id)
    if job.connection_binding and public_publish_authorized is not True:raise ValueError('Explicit public publication authority required')
    if job.state not in {'CONTAINER_CREATED','WAITING_MEDIA'}:raise ValueError('Cannot repeat a publishing attempt')
    await _valid(session,job,provider,media_sha256)
    # Persist the claim before the provider edge. A crash after this point is
    # reconciliation-only, never automatic resubmission.
    job.state='PUBLISHING';job.updated_at=now();await session.commit()
    try:media_id=await provider.publish_container(job.container_id)
    except InstagramProviderError as exc:
        job.error_code=exc.code
        if exc.outcome_unknown or exc.code=='INSTAGRAM_ALREADY_PUBLISHED_RECONCILE':job.state='PUBLISH_UNKNOWN'
        elif exc.code in {'INSTAGRAM_CONTAINER_IN_PROGRESS','INSTAGRAM_READ_FAILED','INSTAGRAM_INVALID_RESPONSE'}:job.state='WAITING_MEDIA'
        else:job.state='FAILED'
        job.updated_at=now();await session.commit();return job
    except Exception:
        job.state='PUBLISH_UNKNOWN';job.error_code='INSTAGRAM_OUTCOME_UNKNOWN';job.updated_at=now();await session.commit();return job
    job.media_id=media_id;job.state='PUBLISHED_ID_KNOWN';job.error_code=None;job.updated_at=now();await session.commit();return job

async def reconcile(session,job_id,*,provider):
    job=await _locked(session,job_id)
    if job.state in {'CREATING','PUBLISHING'}:raise ValueError('An active or crashed claim needs operator reconciliation; no overlapping provider action')
    if job.connection_binding:await validate_provider_binding(session,job,provider)
    if provider.account_id!=job.account_id:raise ValueError('Pinned account mismatch')
    if job.state=='CANCELLED':raise ValueError('Cancelled draft has no provider result to reconcile')
    if job.media_id:
        result=await provider.published_media(job.media_id)
        job.permalink=result['permalink'];job.state='PUBLISHED';job.error_code=None
    elif job.container_id:
        result=await provider.container_status(job.container_id)
        if result.status=='PUBLISHED':job.state='PUBLISHED_ID_UNKNOWN'
        elif result.status in {'ERROR','EXPIRED'}:job.state='FAILED';job.error_code='INSTAGRAM_CONTAINER_'+result.status
        # FINISHED after lost response cannot prove the publish was not accepted.
        # Keep UNKNOWN/CREATING/PUBLISHING until an operator resolves it.
    job.updated_at=now();await session.commit();return job

async def cancel_draft(session,job_id):
    """Cancel only an unclaimed draft; never imply a provider action was undone."""
    job=await _locked(session,job_id)
    if job.state!='DRAFT':raise ValueError('Only an unclaimed draft can be cancelled; provider attempts require reconciliation')
    job.state='CANCELLED';job.updated_at=now();await session.commit();return job

async def mark_interrupted_claim_unknown(session,job_id,*,expected_state,expected_updated_at,operator_confirmed_stopped=False):
    """Internal operator recovery. No timeout guessing and no provider resubmission.

    A future owner-only administrative surface must authenticate the operator and
    establish the worker has stopped. This function is not an authority record.
    A stale observation cannot change a newer claim or a completed attempt.
    """
    if operator_confirmed_stopped is not True:raise ValueError('Operator must establish that the worker stopped; age alone is not evidence')
    if expected_state not in {'CREATING','PUBLISHING'}:raise ValueError('Only an interrupted provider mutation claim can be marked unknown')
    job=await _locked(session,job_id)
    if job.state!=expected_state or job.updated_at!=expected_updated_at:raise ValueError('Claim changed; reread before reconciliation')
    job.state='CREATE_UNKNOWN' if expected_state=='CREATING' else 'PUBLISH_UNKNOWN'
    job.error_code='INSTAGRAM_INTERRUPTED_CLAIM_UNKNOWN';job.updated_at=now();await session.commit();return job

async def validate_provider_binding(session,job,provider):
    mode=job.connection_binding.get('login_mode')
    if mode=='INSTAGRAM_LOGIN':
        from app.application.instagram_direct_execution import validate_binding
        host='https://graph.instagram.com/v27.0'
    elif mode=='UNIFIED':
        from app.application.instagram_unified_execution import validate_binding
        host='https://graph.facebook.com/v27.0'
    else:raise ValueError('Explicit supported connection provenance required')
    if getattr(provider,'graph_base',None)!=host:raise ValueError('Provider host does not match pinned connection; no fallback')
    await validate_binding(session,job)
