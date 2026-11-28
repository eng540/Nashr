"""Private batch review only. No execution core, providers, bytes or grants."""
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo
import re
from sqlalchemy import select, text, func
from app.infrastructure.database.models import (ArtifactModel as Artifact, PlatformCopyModel as Copy,
    DistributionSelectionModel as Selection, InstagramConnectionModel as Connection,
    InstagramExecutionModel as Job, InstagramPrivateBatchReviewModel as Batch)
from app.application import instagram_plan_review as review, instagram_unified_execution as execution
from app.application.distribution_readiness import source_fingerprint, selection_version
from app.application.exact_schedule_time import timing
from app.application.instagram_oauth import configuration_for, digest

MAX_ITEMS=20

def entries(values):
    if not 1<=len(values)<=MAX_ITEMS:raise ValueError('اختر من مادة واحدة إلى20مادة بالترتيب نفسه.')
    result=[]
    for item in values:
        if set(item)!={'artifact_id','due_at','timezone','share_to_feed'}:raise ValueError('حدد المادة والوقت والمنطقة وخيار الخلاصة صراحةً.')
        if item['share_to_feed'] is not None and type(item['share_to_feed']) is not bool:raise ValueError('خيار الخلاصة غير صالح.')
        when=timing(item['due_at'],item['timezone'],now=datetime.now(timezone.utc))
        result.append(dict(artifact_id=str(UUID(str(item['artifact_id']))),due_at=when['due_at'],timezone=when['timezone'],share_to_feed=item['share_to_feed']))
    if len({v['artifact_id'] for v in result})!=len(result):raise ValueError('المواد المكررة غير مسموحة.')
    return result

async def preview(session,values):
    requested=entries(values);rows=[];saveable=True
    config=await configuration_for(session)
    conn=await session.get(Connection,1,populate_existing=True)
    binding=review.fingerprint([config['fingerprint'],conn.connected_at if conn else None,
        conn.client_business_id if conn else None,digest(conn.token_ciphertext) if conn else None])
    for item in requested:
        uid=UUID(item['artifact_id']);original=await session.get(Artifact,uid,populate_existing=True)
        if original is None or original.kind=='POST' or (original.artifact_metadata or {}).get('source_type')=='PLATFORM_VARIANT':
            raise ValueError('اختر المواد الأصلية نفسها دون منشورات أو نسخ مشتقة.')
        selection=await session.get(Selection,uid,populate_existing=True)
        p=await review.preview(session,uid,share_to_feed=item['share_to_feed'],planned_at=datetime.fromisoformat(item['due_at']).astimezone(ZoneInfo(item['timezone'])),timezone_name=item['timezone'])
        blockers=list(p['blockers'])
        platforms=list(selection.platforms) if selection else []
        stale=bool(selection and selection.source_fingerprint!=source_fingerprint(original))
        if not selection or 'instagram' not in platforms:blockers.append('Instagram مستبعد أو لم يُختر لهذه المادة. لم نغير الوجهات أو نستبدل المادة.')
        if stale:blockers.append('اختيار الوجهات قديم؛ راجعه واحفظه صراحةً قبل التنفيذ.')
        jobs=(await session.execute(select(Job).where(Job.artifact_id==uid).order_by(Job.created_at.desc(),Job.id.desc()).limit(30).execution_options(populate_existing=True))).scalars().all()
        count=await session.scalar(select(func.count()).select_from(Job).where(Job.artifact_id==uid))
        history=[await execution.describe_result(session,j) for j in jobs]
        # Do not treat another account's result as delivery for this account.
        account=(p.get('account') or {}).get('account_id')
        conflicts=await session.scalar(select(func.count()).select_from(Job).where(Job.artifact_id==uid,Job.account_id==account,Job.state!='CANCELLED')) if account else 0
        if conflicts:blockers.append('توجد عملية أو نتيجة سابقة للحساب نفسه، حتى لو فشلت أو غمضت. راجع سجلها؛ لا إعادة نشر ضمنية.')
        if original.kind=='VIDEO' and type(item['share_to_feed']) is not bool:saveable=False
        saveable=saveable and p['can_save_draft']
        rows.append(dict(**item,kind=original.kind,source_fingerprint=p['source_fingerprint'],copy_version=p['copy_version'],
            selected_platforms=platforms,selection_version=selection_version(selection),selection_stale=stale,
            caption=p['caption'],alt_text=p['alt_text'],account=p['account'],inspection=p['inspection'],pending=p['pending'],
            blockers=list(dict.fromkeys(blockers)),history=history,history_total=count,history_truncated=count>len(history)))
    snapshot=dict(items=rows,connection_binding_digest=binding)
    return dict(**snapshot,preview_hash=review.fingerprint(snapshot),can_save_draft=saveable,
        blocked_count=sum(bool(r['blockers']) for r in rows),execution_enabled=False,media_exposure_enabled=False,
        approval_recorded=False,scheduled=False,
        caveat='مراجعة خاصة من السجل المحفوظ فقط، لا تحقق جديد من Meta أو بايتات الوسيط. الحفظ ليس جدولاً ولا موافقة نشر أو إتاحة للوسيط. نجاح مادة لدى Meta لا يضمن نجاح بقية الدفعة.')

async def save(session,values,*,preview_hash,request_key):
    if session.in_transaction():raise ValueError('يلزم بدء معاملة مستقلة للمراجعة كاملة.')
    requested=entries(values)
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{8,100}',request_key):raise ValueError('مفتاح حفظ ثابت مطلوب.')
    request_hash=review.fingerprint(requested)
    async with session.begin():
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(606034)')):raise ValueError('توجد مراجعة دفعة أخرى؛ حدّث القراءة قبل المحاولة.')
        previous=await session.scalar(select(Batch).where(Batch.request_key==request_key).with_for_update(nowait=True))
        if previous:
            if previous.request_hash!=request_hash or previous.snapshot_hash!=preview_hash:raise ValueError('مفتاح الحفظ يخص مراجعة أخرى. لم نغيرها.')
            return describe(previous)
        ids=sorted(UUID(i['artifact_id']) for i in requested)
        for model,column in [(Artifact,Artifact.id),(Copy,Copy.artifact_id),(Selection,Selection.artifact_id)]:
            await session.execute(select(model).where(column.in_(ids)).order_by(column).with_for_update(nowait=True).execution_options(populate_existing=True))
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(606024)')):raise ValueError('يتغير ربط الحساب؛ حدّث القراءة.')
        await session.execute(select(Connection).where(Connection.id==1).with_for_update(nowait=True).execution_options(populate_existing=True))
        current=await preview(session,values)
        if current['preview_hash']!=preview_hash or not current['can_save_draft']:raise ValueError('تغير المحتوى أو الاختيار أو الحساب أو الفحص أو السجل. أعد مراجعة الدفعة كاملة.')
        row=Batch(request_key=request_key,request_hash=request_hash,snapshot_hash=preview_hash,snapshot=current,state='DRAFT',created_at=datetime.now(timezone.utc))
        session.add(row);await session.flush()
        return describe(row)

def describe(row):
    return dict(id=str(row.id),state=row.state,snapshot_hash=row.snapshot_hash,snapshot=row.snapshot,
        created_at=row.created_at.isoformat(),execution_enabled=False,scheduled=False,approval_recorded=False,media_exposure_enabled=False)

async def inspect(session,row):
    value=describe(row)
    try:
        current=await preview(session,[dict(artifact_id=i['artifact_id'],due_at=datetime.fromisoformat(i['due_at']),timezone=i['timezone'],share_to_feed=i['share_to_feed']) for i in row.snapshot['items']])
        value['stale']=current['preview_hash']!=row.snapshot_hash
    except ValueError:value['stale']=True
    return value

async def history(session,limit=20):
    # Listing never fans out 20 complete currentness checks. Recheck one exact
    # saved review explicitly, keeping large histories bounded and useful.
    rows=(await session.execute(select(Batch).order_by(Batch.created_at.desc(),Batch.id.desc()).limit(limit))).scalars().all()
    return dict(items=[dict(**describe(row),stale=None) for row in rows],limit=limit,execution_enabled=False,scheduled=False)

async def get_review(session,uid):
    row=await session.get(Batch,uid,populate_existing=True)
    if not row:raise ValueError('مسودة المراجعة غير موجودة.')
    return await inspect(session,row)

async def cancel(session,uid):
    row=await session.scalar(select(Batch).where(Batch.id==uid).with_for_update())
    if not row:raise ValueError('مسودة المراجعة غير موجودة.')
    row.state='CANCELLED';await session.commit()
    return dict(**describe(row),remote_changed=False)
