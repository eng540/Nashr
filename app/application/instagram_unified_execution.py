"""Private Unified-login execution drafts. No media URL, grant, or provider calls.

Public execution remains unavailable. Staging is deliberately not consent.
"""
from sqlalchemy import select,text
from app.infrastructure.database.models import InstagramPlanDraftModel as Review,InstagramExecutionModel as Job,InstagramConnectionModel as Connection
from app.application import instagram_plan_review as review,instagram_execution as core,instagram_oauth as oauth


def describe(job):
    binding=job.connection_binding or {}
    return dict(id=str(job.id),artifact_id=str(job.artifact_id),state=job.state,kind=job.kind,
        account_id=job.account_id,username=binding.get('username'),login_mode=binding.get('login_mode'),
        caption=job.caption,alt_text=job.alt_text,share_to_feed=job.share_to_feed,
        media_sha256=job.media_sha256,copy_version=job.copy_version,created_at=job.created_at.isoformat(),
        container_id=job.container_id,media_id=job.media_id,permalink=job.permalink,error_code=job.error_code,
        execution_enabled=False,media_exposure_enabled=False,approval_recorded=False,
        remaining_gates=['موافقة نشر مستقلة على الحساب والنص والوسيط والوقت.',
            'إذن صريح لإتاحة نسخة الوسيط المحددة لـMeta عند التنفيذ فقط، لا من المعاينة.',
            'إعادة تحقق من الربط وفحص البايتات والصلاحيات قبل التنفيذ.',
            'مسار تنفيذ حي ومصالحة نتائج معتمدان؛ لا تشغيل من هذه المسودة.'])

async def stage(session,uid,review_id):
    # The shared source/copy lock order is taken by save_draft and core.prepare.
    record=await session.get(Review,review_id,populate_existing=True)
    if not record or record.artifact_id!=uid or record.state!='DRAFT' or record.snapshot.get('login_mode','UNIFIED')!='UNIFIED':raise ValueError('مسودة مراجعة Unified لهذه المادة مطلوبة.')
    snapshot=record.snapshot;timing=snapshot.get('timing_intent')
    from datetime import datetime
    # Rebuild and lock the snapshot before creating a private, non-runnable job.
    fresh=await review.save_draft(session,uid,preview_hash=record.snapshot_hash,
        share_to_feed=snapshot.get('share_to_feed'),planned_at=datetime.fromisoformat(timing['local_time']) if timing else None,
        timezone_name=timing['timezone'] if timing else None,login_mode='UNIFIED')
    if fresh['stale'] or snapshot['blockers'] or not snapshot.get('account') or not snapshot.get('inspection'):raise ValueError('المعاينة محجوبة أو تغيرت؛ راجع الحساب والوسيط أولاً.')
    from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel
    await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())
    await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==uid,PlatformCopyModel.platform=='instagram').with_for_update())
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    record=(await session.execute(select(Review).where(Review.id==review_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
    current=await review.preview(session,uid,share_to_feed=snapshot.get('share_to_feed'),planned_at=datetime.fromisoformat(timing['local_time']) if timing else None,timezone_name=timing['timezone'] if timing else None,login_mode='UNIFIED')
    if record.state!='DRAFT' or current['preview_hash']!=record.snapshot_hash:raise ValueError('تغيرت مسودة المراجعة أثناء التثبيت.')
    c=await oauth.configuration_for(session,True);conn=await session.get(Connection,1,populate_existing=True)
    account=oauth.connection_payload(conn,c)
    from datetime import timezone,timedelta
    if conn and (not conn.last_check_at or conn.last_check_ok is not True or conn.last_check_at<datetime.now(timezone.utc)-timedelta(minutes=5)):raise ValueError('يلزم تحقق حديث من الحساب.')
    if not account or account['state']!='CONNECTED_AT_LAST_CHECK' or account['account_id']!=snapshot['account']['account_id'] or account['username']!=snapshot['account']['username']:raise ValueError('تغير ربط الحساب؛ لا مسودة تنفيذ.')
    # Repeated clicks recover the existing draft, including after lost UI replies.
    rows=(await session.execute(select(Job).where(Job.artifact_id==uid,Job.state=='DRAFT'))).scalars().all()
    for job in rows:
        if (job.connection_binding or {}).get('review_id')==str(review_id):return describe(job)
    from uuid import UUID
    job=await core.prepare(session,uid,account_id=account['account_id'],media_sha256=snapshot['inspection']['sha256'],
        copy_version=snapshot['copy_version'],fingerprint=snapshot['source_fingerprint'],
        inspection_id=UUID(snapshot['inspection']['id']),share_to_feed=snapshot.get('share_to_feed'),
        connection_binding=dict(login_mode='UNIFIED',config_hash=c['fingerprint'],connected_at=conn.connected_at.isoformat(),client_business_id=conn.client_business_id,token_hash=oauth.digest(conn.token_ciphertext),username=account['username'],review_id=str(review_id),review_hash=record.snapshot_hash))
    return describe(job)

async def history(session,uid):
    rows=(await session.execute(select(Job).where(Job.artifact_id==uid).order_by(Job.created_at.desc()).limit(30))).scalars().all()
    return {'items':[describe(r) for r in rows if (r.connection_binding or {}).get('login_mode')=='UNIFIED'],'execution_enabled':False}

async def validate_binding(session,job):
    binding=job.connection_binding or {}
    if binding.get('login_mode')!='UNIFIED':raise ValueError('Unified connection provenance required')
    from uuid import UUID
    record=await session.get(Review,UUID(binding['review_id']),populate_existing=True)
    if not record or record.state!='DRAFT' or record.snapshot_hash!=binding['review_hash']:raise ValueError('Review draft changed or cancelled')
    c=await oauth.configuration_for(session,True);conn=await session.get(Connection,1,populate_existing=True)
    account=oauth.connection_payload(conn,c)
    from datetime import datetime,timezone,timedelta
    if conn and (not conn.last_check_at or conn.last_check_ok is not True or conn.last_check_at<datetime.now(timezone.utc)-timedelta(minutes=5)):raise ValueError('يلزم تحقق حديث من الحساب.')
    if not account or account['state']!='CONNECTED_AT_LAST_CHECK' or binding['config_hash']!=c['fingerprint'] or job.account_id!=account['account_id'] or binding['username']!=account['username'] or binding.get('connected_at')!=conn.connected_at.isoformat() or binding.get('client_business_id')!=conn.client_business_id or binding.get('token_hash')!=oauth.digest(conn.token_ciphertext):raise ValueError('Unified connection changed or disabled')
    return account

async def verified_provider(session,job,client):
    """Read-only future-worker factory. No caller route invokes this today.

    Token never leaves this object. Callers still owe explicit source-grounded
    publication/disclosure authority, gated media access and durable execution.
    """
    await validate_binding(session,job)
    conn=await session.get(Connection,1,populate_existing=True)
    from app.adapters.publishing.instagram import InstagramPublisher,InstagramProviderError
    try:
        c=await oauth.configuration_for(session,True)
        token=oauth.cipher(c).decrypt(conn.token_ciphertext.encode()).decode()
        provider=InstagramPublisher(client=client,token=token,account_id=job.account_id)
        facts=await provider.verify_account(app_access_token=c['META_APP_ID']+'|'+c['META_APP_SECRET'],expected_app_id=c['META_APP_ID'])
        if facts['username']!=job.connection_binding['username'] or facts['client_business_id']!=job.connection_binding['client_business_id']:
            raise ValueError('Unified identity changed')
    except Exception:raise ValueError('Unified account verification failed; no provider mutation') from None
    await validate_binding(session,job)
    return provider
