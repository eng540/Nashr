"""Bounded local agent actions. Free text is context, never executable authority.

No language model, cost, provider, grants, publication or scheduling action is
available to this first version. Selected operation/materials are explicit.
"""
import hashlib,json
from datetime import datetime,timezone
from sqlalchemy import select,text
from app.infrastructure.database.models import NashrAgentTaskModel as Task,ArtifactModel as Artifact
from app.application.distribution_readiness import source_fingerprint,get_readiness

ACTIONS={'AUDIT_READINESS':'فحص الجاهزية','PREPARE_COPIES':'تجهيز نسخ بالنص الأصلي'}
def now():return datetime.now(timezone.utc)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def describe(t):
    return dict(id=str(t.id),request_text=t.request_text,plan_hash=t.plan_hash,plan=t.plan,state=t.state,
        completed_steps=t.cursor,total_steps=len(t.plan['items']),results=t.results,created_at=t.created_at.isoformat(),updated_at=t.updated_at.isoformat(),
        publication_authorized=False,ai_used=False,new_cost=False)

async def preview(s,*,request_text,action,artifact_ids):
    if action not in ACTIONS or not 1<=len(artifact_ids)<=20 or len(set(artifact_ids))!=len(artifact_ids):raise ValueError('اختر وظيفة واضحة ومن مادة إلى 20 مادة دون تكرار.')
    if not request_text.strip() or len(request_text)>2000:raise ValueError('اكتب وصفاً مختصراً للطلب.')
    items=[]
    for uid in artifact_ids:
        a=await s.get(Artifact,uid,populate_existing=True)
        if not a or a.kind=='POST' or (a.artifact_metadata or {}).get('source_type')=='PLATFORM_VARIANT':raise ValueError('اختر مواد أصلية موجودة في البنك.')
        items.append(dict(artifact_id=str(a.id),source_fingerprint=source_fingerprint(a),kind=a.kind))
    p=dict(request_text=request_text.strip(),action=action,label=ACTIONS[action],items=items,
        scope='PRIVATE_INTERNAL_ONLY',ai_used=False,new_cost=False,publication_authorized=False,
        explanation='الوصف سياق فقط. الوظيفة والمواد المختارة تحددان الخطة؛ لا فهم حر أو توليد بالذكاء الاصطناعي في هذا الإصدار.')
    return dict(plan=p,plan_hash=digest(p))

async def create(s,*,plan_hash,request_key,**kw):
    key=int.from_bytes(hashlib.sha256(request_key.encode()).digest()[:8],'big',signed=True)
    await s.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
    existing=await s.scalar(select(Task).where(Task.request_key==request_key))
    if existing:
        if existing.plan_hash!=plan_hash or existing.request_text!=kw['request_text'].strip() or existing.plan['action']!=kw['action'] or [i['artifact_id']for i in existing.plan['items']]!=[str(i)for i in kw['artifact_ids']]:raise ValueError('مفتاح الطلب مستخدم لخطة أخرى.')
        return describe(existing)
    value=await preview(s,**kw)
    if value['plan_hash']!=plan_hash:raise ValueError('تغيرت الخطة أو المواد، أعد المعاينة.')
    t=Task(request_key=request_key,request_text=value['plan']['request_text'],plan_hash=plan_hash,plan=value['plan'],state='PLANNED',cursor=0,results=[],created_at=now(),updated_at=now())
    s.add(t);await s.commit();return describe(t)

async def command(s,uid,action):
    t=await s.scalar(select(Task).where(Task.id==uid).with_for_update())
    if not t:raise LookupError('المهمة غير موجودة.')
    if action=='start':
        if t.state=='PLANNED':t.state='RUNNING'
        elif t.state!='RUNNING':raise ValueError('المهمة منتهية؛ أنشئ خطة جديدة بدلاً من إعادة التنفيذ.')
    elif action=='stop':
        if t.state in {'PLANNED','RUNNING'}:t.state='STOPPED'
    else:raise ValueError('أمر غير متاح.')
    t.updated_at=now();await s.commit();return describe(t)

async def process_one(s,uid):
    # Each local step and its result commit together. Stop takes the same task
    # lock and returns only after any current local step has committed/rolled back.
    if s.in_transaction():raise ValueError('Fresh step transaction required')
    async with s.begin():
        t=await s.scalar(select(Task).where(Task.id==uid).with_for_update(skip_locked=True))
        if not t or t.state!='RUNNING':return
        if digest(t.plan)!=t.plan_hash:raise ValueError('Persisted plan integrity failed')
        index=t.cursor;item=t.plan['items'][index]
        from uuid import UUID
        a=await s.scalar(select(Artifact).where(Artifact.id==UUID(item['artifact_id'])).with_for_update())
        result=dict(artifact_id=item['artifact_id'],step=index+1)
        if not a or source_fingerprint(a)!=item['source_fingerprint']:
            result.update(state='BLOCKED',message='تغير الأصل بعد الخطة؛ لم تُنفذ هذه الخطوة.')
        elif t.plan['action']=='AUDIT_READINESS':
            r=await get_readiness(s,a.id)
            result.update(state='DONE',central_approval=r['central_approval'],targets=[dict(platform=x['platform'],status=x['copy_status'],blockers=x['copy_blockers'])for x in r['targets']])
        elif t.plan['action']=='PREPARE_COPIES':
            from app.application.central_platform_copies import prepare_copies
            if a.status!='AVAILABLE' or a.review_status!='APPROVED':
                result.update(state='BLOCKED',message='تجهيز النسخ يحتاج أصلاً معتمداً ومتاحاً؛ لم نغير الاعتماد.')
            else:
                values=await prepare_copies(s,a)
                result.update(state='DONE',message='جُهزت النسخ الناقصة فقط بالنص الأصلي. النسخ الحالية والاختيارات لم تتغير.',targets=[dict(platform=x['platform'],status=x['field_status'],blockers=x['blockers'])for x in values])
        else:raise ValueError('Unsupported persisted action')
        t.results=[*t.results,result];t.cursor+=1;t.updated_at=now()
        if t.cursor==len(t.plan['items']):t.state='COMPLETED_WITH_BLOCKERS'if any(x['state']=='BLOCKED' for x in t.results)else 'COMPLETED'

async def process_tasks():
    from app.infrastructure.database.session import SessionFactory
    async with SessionFactory() as s:ids=list(await s.scalars(select(Task.id).where(Task.state=='RUNNING').order_by(Task.created_at).limit(5)))
    for uid in ids:
        try:
            async with SessionFactory() as s:await process_one(s,uid)
        except Exception:
            # No external effect exists; rollback preserves step index. Surface a
            # bounded failure rather than looping silently or claiming success.
            async with SessionFactory() as s:
                t=await s.scalar(select(Task).where(Task.id==uid).with_for_update())
                if t and t.state=='RUNNING':
                    t.state='FAILED';t.results=[*t.results,dict(state='FAILED',message='تعذر تنفيذ الخطوة. لم تُحفظ نتيجة جزئية؛ راجع المادة ثم أنشئ خطة جديدة.')];t.updated_at=now();await s.commit()
