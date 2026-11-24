"""Owner-only Instagram review drafts, never provider calls or execution grants."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text
from app.infrastructure.database.models import (ArtifactModel, PlatformCopyModel,
    PlatformMediaInspectionModel, InstagramConnectionModel, InstagramPlanDraftModel)
from app.application.central_platform_copies import evaluate
from app.application.distribution_readiness import source_fingerprint
from app.application.media_inspection_history import describe
from app.application.instagram_oauth import configuration_for, connection_payload


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


async def preview(session, uid, *, share_to_feed=None):
    row=await session.get(ArtifactModel,uid,populate_existing=True)
    copy=await session.get(PlatformCopyModel,(uid,'instagram'),populate_existing=True)
    if row is None or copy is None or row.kind not in {'IMAGE','VIDEO'}:
        raise ValueError('اختر صورة أو فيديو أصلياً مع نسخة Instagram محفوظة.')
    fields=evaluate(row,copy)
    c=await configuration_for(session)
    connection=await session.get(InstagramConnectionModel,1,populate_existing=True)
    account=connection_payload(connection,c)
    # Never copy scopes, business identity, encrypted settings or token into a draft.
    account={k:account[k] for k in ['account_id','username','state','enabled','expires_at','last_check_at','last_check_ok']} if account else None
    blockers=list(fields['blockers'])
    if c['missing']:blockers.append('إعداد تطبيق Meta في Nashr غير مكتمل؛ لا يثبت ذلك عدم وجود تطبيق لديك.')
    if not account:blockers.append('لم يُربط حساب Instagram مختار بعد.')
    elif account['state']!='CONNECTED_AT_LAST_CHECK':blockers.append('الربط معطل أو يحتاج مراجعة قبل أي نشر لاحق.')
    if account:
        checked=connection.last_check_at
        if not checked or connection.last_check_ok is not True or checked<datetime.now(timezone.utc)-timedelta(minutes=5):
            blockers.append('يلزم تحقق حديث صريح من الحساب قبل أي نشر لاحق.')
    records=(await session.execute(select(PlatformMediaInspectionModel).where(
        PlatformMediaInspectionModel.artifact_id==uid,PlatformMediaInspectionModel.platform=='instagram')
        .order_by(PlatformMediaInspectionModel.created_at.desc(),PlatformMediaInspectionModel.id.desc()).limit(20))).scalars().all()
    chosen=None
    for r in records:
        description=describe(row,copy,r)
        if r.selected and not description['stale']:
            chosen=r;break
    inspection=None
    pending=[]
    if chosen:
        inspection={'id':str(chosen.id),'sha256':chosen.sha256,'created_at':chosen.created_at.isoformat(),
            'media_id':str(chosen.media_id) if chosen.media_id else None,'measurements':chosen.result.get('measurements',{})}
        blockers.extend(chosen.result.get('blockers',[]))
        pending=list(chosen.result.get('pending',[]))
    else:blockers.append('افحص الوسيط المختار واحفظ سجله الخاص من قسم سجل الفحوص أولاً.')
    if row.kind=='VIDEO' and not isinstance(share_to_feed,bool):blockers.append('اختر صراحةً ظهور Reel في الخلاصة أو عدم ظهوره.')
    if row.kind=='IMAGE' and share_to_feed is not None:raise ValueError('خيار الخلاصة يخص Reel فقط.')
    payload={'artifact_id':str(uid),'source_fingerprint':source_fingerprint(row),'copy_version':copy.version,
        'kind':row.kind,'caption':copy.fields['description'],'alt_text':copy.fields['alt_text'],
        'selected_media_id':str(copy.selected_media_id) if copy.selected_media_id else None,
        'share_to_feed':share_to_feed,'account':account,'inspection':inspection,
        'blockers':list(dict.fromkeys(blockers)),'pending':pending,
        'execution_enabled':False,'media_exposure_enabled':False,'outgoing_approval_recorded':False,
        'remaining_steps':['موافقة نشر مستقلة على الحساب والنص والوسيط والوقت، لا من حفظ هذه المسودة.',
            'نسخة وسيط محددة ورابط محدود لـMeta مرتبطان بإذن النشر فقط، وليس بهذه المعاينة.',
            'استكمال فحوص الوسيط المعلقة وقبول Meta الفعلي.']}
    return {**payload,'preview_hash':fingerprint(payload),'can_save_draft':row.review_status=='APPROVED' and row.status=='AVAILABLE' and not fields['source_stale'],
        'caveat':'معاينة خاصة دون قراءة جديدة للملف أو اتصال بـMeta. حفظ المسودة لا ينشئ موعداً أو إذن نشر ولا يكشف الوسيط.'}


async def save_draft(session,uid,*,preview_hash,share_to_feed=None):
    # Match lock order used by source/copy edits. No network or media reads here.
    await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())
    await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id==uid,PlatformCopyModel.platform=='instagram').with_for_update())
    await session.execute(text('SELECT pg_advisory_xact_lock(606024)'))
    await session.execute(select(InstagramConnectionModel).where(InstagramConnectionModel.id==1).with_for_update())
    current=await preview(session,uid,share_to_feed=share_to_feed)
    if current['preview_hash']!=preview_hash:raise ValueError('تغيرت المعاينة أو الحساب أو الفحص؛ اعرضها مجدداً قبل الحفظ.')
    if not current['can_save_draft']:raise ValueError('الأصل أو النسخة لم يعد صالحاً لحفظ مسودة مراجعة.')
    if current['kind']=='VIDEO' and not isinstance(share_to_feed,bool):raise ValueError('اختر ظهور Reel في الخلاصة صراحةً قبل حفظ المسودة.')
    existing=(await session.execute(select(InstagramPlanDraftModel).where(InstagramPlanDraftModel.artifact_id==uid,InstagramPlanDraftModel.snapshot_hash==preview_hash,InstagramPlanDraftModel.state=='DRAFT'))).scalars().first()
    if existing:return await describe_draft(session,existing)
    record=InstagramPlanDraftModel(artifact_id=uid,snapshot_hash=preview_hash,snapshot=current,state='DRAFT')
    session.add(record);await session.commit()
    return await describe_draft(session,record)


async def describe_draft(session,record):
    current=await preview(session,record.artifact_id,share_to_feed=record.snapshot.get('share_to_feed'))
    return {'id':str(record.id),'state':record.state,'created_at':record.created_at.isoformat(),
        'snapshot':record.snapshot,'stale':current['preview_hash']!=record.snapshot_hash,
        'execution_enabled':False,'media_exposure_enabled':False}


async def list_drafts(session,uid):
    rows=(await session.execute(select(InstagramPlanDraftModel).where(InstagramPlanDraftModel.artifact_id==uid)
        .order_by(InstagramPlanDraftModel.created_at.desc()).limit(20))).scalars().all()
    return {'items':[await describe_draft(session,row) for row in rows],'execution_enabled':False}
