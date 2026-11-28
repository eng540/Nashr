"""Individual Unified worker. Each remote action follows a committed exact claim.

Worker secrets are ephemeral. Unknown or abandoned writers are never retried.
No batch activation or supervisor recovery is implemented.
"""
from uuid import UUID,uuid4
from sqlalchemy import select
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import InstagramDispatchModel as Dispatch,InstagramExecutionModel as Job
from app.application import instagram_production_fence as fence,instagram_fenced_media_status as media,instagram_isolated_claims as claims,instagram_execution as core,instagram_publish_decisions as decisions
from app.adapters.publishing.instagram import InstagramProviderError

async def payload(did,provider):
    async with SessionFactory() as s:
        d=await s.get(Dispatch,did)
        if not d:raise ValueError('Dispatch unavailable')
        j=await s.get(Job,d.execution_id)
        if d.state=='PENDING':await decisions.validate(s,j,d.decision_id)
        await core.validate_provider_binding(s,j,provider)
        if provider.account_id!=j.account_id:raise ValueError('Pinned provider account mismatch')
        return dict(kind=j.kind,caption=j.caption,alt_text=j.alt_text,share_to_feed=j.share_to_feed,container_id=j.container_id)

async def row(did):
    async with SessionFactory() as s:return await s.get(Dispatch,did)

async def run(did,*,provider,grant_url_factory):
    p=await payload(did,provider);worker='individual-'+str(uuid4());secret=claims.token()
    async with SessionFactory() as s:
        receipt,capability=await fence.first_grant_and_claim(s,did,request_key=str(uuid4()),worker_id=worker,ownership_token=secret)
    outcome='STOPPED_WITHOUT_WRITE';container=None
    try:
        url=grant_url_factory(UUID(receipt['grant_id']),capability)
        outcome='UNKNOWN'
        container=await provider.create_container(**receipt['payload'],media_url=url)
        outcome='CONTAINER_KNOWN'
    except InstagramProviderError as exc:outcome='UNKNOWN'if exc.outcome_unknown else 'DEFINITE_REJECTION'
    except Exception:pass
    async with SessionFactory() as s:
        await fence.finish_create(s,did,claim_id=UUID(receipt['id']),ownership_token=secret,worker_id=worker,expected_claim_version=0,outcome=outcome,container_id=container)
    if outcome=='CONTAINER_KNOWN':await resume(did,provider=provider)
    return await row(did)

async def resume(did,*,provider):
    p=await payload(did,provider);worker='individual-'+str(uuid4());secret=claims.token()
    async with SessionFactory() as s:
        receipt=await media.claim_status(s,did,request_key=str(uuid4()),worker_id=worker,ownership_token=secret)
    status='READ_FAILED';backoff=60
    try:
        result=await provider.container_status(receipt['container_id'])
        if result.container_id!=receipt['container_id']:raise ValueError('Read identity changed')
        status=result.status
    except InstagramProviderError as exc:
        if exc.code=='INSTAGRAM_RATE_LIMITED':status='RATE_LIMITED';backoff=exc.retry_after_seconds or 60
    except Exception:pass
    async with SessionFactory() as s:
        done=await media.finish_status(s,did,claim_id=UUID(receipt['id']),worker_id=worker,ownership_token=secret,expected_claim_version=0,status=status,retry_after_seconds=backoff)
    if done['state']!='COMPLETED' or status!='FINISHED':return await row(did)
    secret=claims.token()
    try:
        async with SessionFactory() as s:
            write=await media.claim_publish(s,did,status_claim_id=UUID(receipt['id']),request_key=str(uuid4()),worker_id=worker,ownership_token=secret)
    except ValueError:return await row(did) # Stop/expiry/changed bytes, no POST.
    outcome='UNKNOWN';mid=None
    try:
        mid=await provider.publish_claimed_container(write['container_id']);outcome='PUBLISHED'
    except InstagramProviderError as exc:outcome='UNKNOWN'if exc.outcome_unknown else 'DEFINITE_REJECTION'
    except Exception:pass
    async with SessionFactory() as s:
        await media.finish_publish(s,did,claim_id=UUID(write['id']),worker_id=worker,ownership_token=secret,expected_claim_version=0,outcome=outcome,media_id=mid)
    return await row(did)


async def reconcile(did,*,provider):
    await payload(did,provider)
    worker='individual-'+str(uuid4());secret=claims.token()
    async with SessionFactory() as s:
        receipt=await media.claim_status(s,did,request_key=str(uuid4()),worker_id=worker,ownership_token=secret)
    args=dict(claim_id=UUID(receipt['id']),worker_id=worker,ownership_token=secret,expected_claim_version=0)
    if receipt['media_id']:
        try:
            result=await provider.published_media(receipt['media_id'])
            if result['media_id']!=receipt['media_id'] or result['account_id']!=provider.account_id:raise ValueError('Exact result identity changed')
        except InstagramProviderError as exc:
            async with SessionFactory() as s:await media.finish_status(s,did,**args,status='RATE_LIMITED' if exc.code=='INSTAGRAM_RATE_LIMITED' else 'READ_FAILED',retry_after_seconds=exc.retry_after_seconds or 60)
        except Exception:
            async with SessionFactory() as s:await media.finish_status(s,did,**args,status='READ_FAILED')
        else:
            async with SessionFactory() as s:await media.finish_permalink(s,did,**args,media_id=result['media_id'],permalink=result['permalink'])
    else:
        status='READ_FAILED';backoff=60
        try:
            result=await provider.container_status(receipt['container_id'])
            if result.container_id!=receipt['container_id']:raise ValueError('Read identity changed')
            status=result.status
        except InstagramProviderError as exc:
            if exc.code=='INSTAGRAM_RATE_LIMITED':status='RATE_LIMITED';backoff=exc.retry_after_seconds or 60
        except Exception:pass
        async with SessionFactory() as s:await media.finish_status(s,did,**args,status=status,retry_after_seconds=backoff)
    return await row(did)
