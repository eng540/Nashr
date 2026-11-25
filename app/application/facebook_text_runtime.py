"""Exact Page text execution. No media, implicit retries or native scheduling."""
import json
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text, or_
import httpx
from app.infrastructure.database.models import FacebookExecutionModel as Job, ArtifactModel, FacebookPageConnectionModel as Connection
from app.application import facebook_execution as core, facebook_reel_runtime as reels, facebook_page_oauth as oauth
from app.application.instagram_plan_review import fingerprint
from app.application.distribution_readiness import source_fingerprint
from app.application.exact_schedule_time import timing
from app.adapters.publishing.facebook import FacebookPagePublisher, FacebookProviderError
LOCK=606032

def now():
    return datetime.now(timezone.utc)

def describe(j):
    return dict(id=str(j.id), artifact_id=str(j.artifact_id), state=j.state,
                snapshot=j.runtime_snapshot, snapshot_hash=j.runtime_hash,
                approved=bool(j.evidence_ref), post_id=j.post_id, permalink=j.permalink,
                error_code=j.error_code, updated_at=j.updated_at.isoformat(),
                no_automatic_retry=True, kind='FACEBOOK_PAGE_TEXT')

async def facts(s, uid):
    a,p=await core.original(s,uid)
    if a.kind!='TEXT':
        raise ValueError('مسار النص لا يقبل صورة أو فيديو. لا تحويل أو حذف للمحتوى.')
    return dict(artifact_id=str(uid),source_fingerprint=source_fingerprint(a),copy_version=p.version,
                message=p.fields['description'],connection=await reels.binding(s),
                audience='FACEBOOK_PAGE_PUBLIC_TEXT',fields=dict(p.fields))

async def stage(s,uid,*,due_at=None,timezone_name=None):
    scheduled=timing(due_at,timezone_name,now=now()) if due_at is not None or timezone_name is not None else None
    snap={**await facts(s,uid),'time':'NOW_AFTER_EXPLICIT_APPROVAL'}
    if scheduled:snap.update(time='APP_LOCAL_SCHEDULED',**scheduled)
    h=fingerprint(snap)
    unresolved=(await s.execute(select(Job).where(Job.artifact_id==uid,Job.runtime_snapshot.is_not(None),Job.state.in_(['SENDING','OUTCOME_UNKNOWN'])))).scalars().first()
    if unresolved:
        raise ValueError('توجد محاولة إرسال غير محسومة. لا ننشئ قراراً يعيد النص قبل التحقق منها.')
    old=(await s.execute(select(Job).where(Job.artifact_id==uid,Job.runtime_hash==h,Job.runtime_snapshot.is_not(None),Job.state.in_(['DRAFT','APPROVED','SENDING','OUTCOME_UNKNOWN','POST_ID_KNOWN','PUBLISHED_AT_LAST_CHECK','RESULT_CHANGED','NOT_CONFIRMED_PUBLISHED'])))).scalars().first()
    if old:return describe(old)
    # Reuse the established text lifecycle table and exact-copy validator. Legacy
    # dormant rows remain unbound and can never enter the runtime scanner.
    j=Job(artifact_id=uid,page_id=snap['connection']['page_id'],source_fingerprint=snap['source_fingerprint'],copy_version=snap['copy_version'],kind='TEXT',message=snap['message'],total_bytes=0,state='DRAFT',runtime_snapshot=snap,runtime_hash=h,due_at=datetime.fromisoformat(scheduled['due_at']) if scheduled else None,created_at=now(),updated_at=now())
    s.add(j);await s.commit()
    return describe(j)

async def validate(s,j,*,approval=False):
    if not j.runtime_snapshot or j.kind!='TEXT' or fingerprint(j.runtime_snapshot)!=j.runtime_hash:
        raise ValueError('محاولة غير مربوطة بمعاينة نصية صريحة.')
    snap=j.runtime_snapshot
    expected_due=datetime.fromisoformat(snap['due_at']) if snap.get('due_at') else None
    if (j.due_at!=expected_due or
        j.source_fingerprint!=snap['source_fingerprint'] or j.copy_version!=snap['copy_version'] or
        j.message!=snap['message'] or j.page_id!=snap['connection']['page_id'] or
        j.total_bytes!=0 or j.mime_type is not None or j.media_sha256 is not None):
        raise ValueError('تغير النص المثبت أو الصفحة.')
    f=await facts(s,j.artifact_id)
    if any(j.runtime_snapshot.get(k)!=v for k,v in f.items()):
        raise ValueError('تغير الأصل أو نسخة Facebook أو ربط الصفحة. راجع قراراً جديداً.')
    if not approval and (not j.evidence_ref or not j.approved_until or j.approved_until<=now()):
        raise ValueError('انتهى قرار التنفيذ أو لا توجد موافقة صريحة.')

async def approve(s,j,h,evidence):
    if j.state!='DRAFT' or j.runtime_hash!=h or not re.fullmatch(r'(owner-session|trusted-message):[A-Za-z0-9_.:-]{8,240}',evidence):
        raise ValueError('اعتمد المعاينة الحالية فقط.')
    await validate(s,j,approval=True)
    if j.due_at:timing(j.due_at,j.runtime_snapshot['timezone'],now=now())
    j.evidence_ref=evidence;j.approved_until=(j.due_at or now())+timedelta(minutes=30)
    j.state='APPROVED';j.updated_at=now();await s.commit()
    return describe(j)

async def provider(s,j,client):
    # This is read-only provider validation; current app/account truth, never a
    # historical successful Reel or the mere existence of saved credentials.
    await oauth.verify_saved_connection(s)
    if await reels.binding(s)!=j.runtime_snapshot['connection']:
        raise ValueError('تغيرت الصفحة أو صلاحياتها؛ لا إرسال إلى بديل.')
    r=await s.get(Connection,1,populate_existing=True)
    token=json.loads(oauth.key().decrypt(r.token_ciphertext.encode()))['page_token']
    return FacebookPagePublisher(client=client,token=token,page_id=r.page_id,version='v27.0')

async def process_one(s,j):
    if j.state=='APPROVED' and j.due_at and j.due_at>now():return
    # Only known-ID recovery is independent of the former content/approval expiry.
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
        if j.post_id:
            p=await provider(s,j,client)
            await core.reconcile(s,j.id,provider=p)
            return
        if j.state!='APPROVED':return
        await validate(s,j)
        p=await provider(s,j,client)
        await validate(s,j) # recheck exact approval/content after remote reads
        j.state='SENDING';j.updated_at=now();await s.commit()
        try:
            result=await p.publish_text(message=j.message,authorized=True,public_page_acknowledged=True)
            # A known ID is not publication proof. Persist it before readback.
            post=p.post_identity(result.post_id)
            if result.state!='POST_ID_KNOWN':raise ValueError()
            j.post_id=post;j.state='POST_ID_KNOWN';j.updated_at=now();await s.commit()
        except Exception as exc:
            j.state='FAILED' if isinstance(exc,FacebookProviderError) and not exc.outcome_unknown else 'OUTCOME_UNKNOWN'
            j.error_code=exc.code if isinstance(exc,FacebookProviderError) else 'FACEBOOK_TEXT_OUTCOME_UNKNOWN'
            j.updated_at=now();await s.commit();return
        await core.reconcile(s,j.id,provider=p)

async def process_approved():
    from app.infrastructure.database.session import SessionFactory,engine
    async with engine.connect() as lock,SessionFactory() as s:
        if not (await lock.execute(text(f'SELECT pg_try_advisory_lock({LOCK})'))).scalar():return
        try:
            interrupted=(await s.execute(select(Job).where(Job.runtime_snapshot.is_not(None),Job.state=='SENDING'))).scalars().all()
            for j in interrupted:
                j.state='OUTCOME_UNKNOWN';j.error_code='FACEBOOK_TEXT_INTERRUPTED';j.updated_at=now()
            await s.commit()
            rows=(await s.execute(select(Job).where(Job.runtime_snapshot.is_not(None),Job.kind=='TEXT',or_( (Job.state=='APPROVED') & or_(Job.due_at.is_(None),Job.due_at<=now()), (Job.state.in_(['POST_ID_KNOWN','NOT_CONFIRMED_PUBLISHED'])) & Job.post_id.is_not(None))).order_by(Job.updated_at).limit(3))).scalars().all()
            for j in rows:
                jid=j.id
                try:await process_one(s,j)
                except Exception as exc:
                    await s.rollback();j=await s.get(Job,jid,populate_existing=True)
                    j.error_code=getattr(exc,'code','FACEBOOK_TEXT_CHECK_FAILED')
                    if j.state=='SENDING':j.state='OUTCOME_UNKNOWN'
                    elif not j.post_id:j.state='BLOCKED'
                    j.updated_at=now();await s.commit()
        finally:
            await lock.execute(text(f'SELECT pg_advisory_unlock({LOCK})'));await lock.commit()

async def cancel(s,j):
    if not j.runtime_snapshot or j.state not in {'DRAFT','APPROVED'}:
        raise ValueError('لا يلغي الإلغاء المحلي إرسالاً بدأ أو منشوراً لدى Meta.')
    j.state='CANCELLED';j.updated_at=now();await s.commit()
    return describe(j)
