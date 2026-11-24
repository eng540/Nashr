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

async def prepare(session,uid,*,account_id,media_sha256,copy_version,fingerprint,share_to_feed=None):
    import re
    if not ID.fullmatch(account_id) or not re.fullmatch(r'[a-f0-9]{64}',media_sha256):raise ValueError('Invalid pinned account or media digest')
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())).scalar_one_or_none()
    copy=await session.get(PlatformCopyModel,(uid,'instagram'))
    if row is None or copy is None or row.review_status!='APPROVED' or row.status!='AVAILABLE' or row.kind not in {'IMAGE','VIDEO'}:raise ValueError('Approved original image or video required')
    if source_fingerprint(row)!=fingerprint or copy.source_fingerprint!=fingerprint or copy.version!=copy_version:raise ValueError('Source or copy changed')
    if row.kind=='VIDEO' and not isinstance(share_to_feed,bool):raise ValueError('Explicit Reel feed choice required')
    from app.application.central_platform_copies import evaluate
    if evaluate(row,copy)['field_status']!='FIELDS_VALIDATED':raise ValueError('Instagram fields are blocked')
    job=Job(artifact_id=uid,account_id=account_id,source_fingerprint=fingerprint,copy_version=copy_version,media_sha256=media_sha256,kind=row.kind,caption=copy.fields['description'],alt_text=copy.fields['alt_text'],share_to_feed=share_to_feed,state='DRAFT',created_at=now(),updated_at=now())
    session.add(job);await session.commit();return job

async def _locked(session,job_id):
    job=(await session.execute(select(Job).where(Job.id==job_id).with_for_update())).scalar_one_or_none()
    if job is None:raise ValueError('Execution record not found')
    return job

async def _valid(session,job,provider,media_sha256):
    if provider.account_id!=job.account_id or media_sha256!=job.media_sha256:raise ValueError('Pinned account or media changed')
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==job.artifact_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    copy=await session.get(PlatformCopyModel,(job.artifact_id,'instagram'),populate_existing=True)
    if row is None or copy is None or row.review_status!='APPROVED' or row.status!='AVAILABLE' or source_fingerprint(row)!=job.source_fingerprint or copy.source_fingerprint!=job.source_fingerprint or copy.version!=job.copy_version:raise ValueError('Original or platform copy changed; no execution')

async def create_container(session,job_id,*,provider,media_url,media_sha256,authorized=False):
    if authorized is not True:raise ValueError('Explicit publishing authority required; preview does not authorize media access')
    job=await _locked(session,job_id)
    if job.state!='DRAFT':raise ValueError('Container creation already attempted; never repeat unknown outcomes')
    await _valid(session,job,provider,media_sha256)
    job.state='CREATING';job.updated_at=now();await session.commit()
    try:container=await provider.create_container(kind=job.kind,media_url=media_url,caption=job.caption,alt_text=job.alt_text,share_to_feed=job.share_to_feed)
    except InstagramProviderError as exc:
        job.state='CREATE_UNKNOWN' if exc.outcome_unknown else 'FAILED';job.error_code=exc.code;job.updated_at=now();await session.commit();return job
    except Exception:
        job.state='CREATE_UNKNOWN';job.error_code='INSTAGRAM_OUTCOME_UNKNOWN';job.updated_at=now();await session.commit();return job
    job.container_id=container;job.state='CONTAINER_CREATED';job.updated_at=now();await session.commit();return job

async def publish(session,job_id,*,provider,media_sha256,authorized=False):
    if authorized is not True:raise ValueError('Explicit publishing authority required')
    job=await _locked(session,job_id)
    if job.state not in {'CONTAINER_CREATED','WAITING_MEDIA'}:raise ValueError('Cannot repeat a publishing attempt')
    await _valid(session,job,provider,media_sha256)
    # Persist the claim before the provider edge. A crash after this point is
    # reconciliation-only, never automatic resubmission.
    job.state='PUBLISHING';job.updated_at=now();await session.commit()
    try:media_id=await provider.publish_container(job.container_id)
    except InstagramProviderError as exc:
        job.error_code=exc.code
        if exc.outcome_unknown or exc.code=='INSTAGRAM_ALREADY_PUBLISHED_RECONCILE':job.state='PUBLISH_UNKNOWN'
        elif exc.code=='INSTAGRAM_CONTAINER_IN_PROGRESS':job.state='WAITING_MEDIA'
        else:job.state='FAILED'
        job.updated_at=now();await session.commit();return job
    except Exception:
        job.state='PUBLISH_UNKNOWN';job.error_code='INSTAGRAM_OUTCOME_UNKNOWN';job.updated_at=now();await session.commit();return job
    job.media_id=media_id;job.state='PUBLISHED_ID_KNOWN';job.error_code=None;job.updated_at=now();await session.commit();return job

async def reconcile(session,job_id,*,provider):
    job=await _locked(session,job_id)
    if job.state in {'CREATING','PUBLISHING'}:raise ValueError('An active or crashed claim needs operator reconciliation; no overlapping provider action')
    if provider.account_id!=job.account_id:raise ValueError('Pinned account mismatch')
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
