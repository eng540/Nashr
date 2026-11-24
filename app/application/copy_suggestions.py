"""Optional, non-authoritative copy proposals. Live provider intentionally disabled.

The production runtime never resolves a provider here. A configured API key does
not establish permission to spend or send source material to a provider. Tests
may inject a provider explicitly to exercise the suggestion workflow.
"""
from copy import deepcopy
from hashlib import sha256
import json
from typing import Protocol

from app.application.central_platform_copies import FIELDS,evaluate
from app.application.distribution_readiness import source_fingerprint

SUPPORTED={'telegram','youtube','instagram'}
PROMPT_VERSION='platform-copy-suggestion-v1'

class SuggestionProvider(Protocol):
    async def suggest(self,*,platform:str,source:dict,fields:dict)->dict: ...


def fields_digest(fields):
    return sha256(json.dumps(fields,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_fields(fields):
    if not isinstance(fields,dict) or set(fields)!=FIELDS:
        raise ValueError('حقول الاقتراح لا تطابق حقول النسخة.')
    if any(not isinstance(fields[k],str) or len(fields[k])>50000 for k in FIELDS-{'tags'}):
        raise ValueError('نص الاقتراح غير صالح أو يتجاوز حد التخزين.')
    tags=fields['tags']
    if not isinstance(tags,list) or len(tags)>100 or any(not isinstance(t,str) or not t.strip() or len(t)>500 for t in tags):
        raise ValueError('وسوم الاقتراح غير صالحة.')
    return deepcopy(fields)


async def propose(row,copy,provider:SuggestionProvider|None=None):
    """No mutation. Provider failures return the exact saved fields as fallback."""
    current=deepcopy(copy.fields)
    result={'state':'SERVICE_DISABLED','fields':current,'source_fingerprint':source_fingerprint(row),
        'copy_version':copy.version,'fields_digest':fields_digest(current),'prompt_version':PROMPT_VERSION,
        'applied':False,'content_changed':False,'execution_authorized':False,
        'reason':'التوليد الحي غير مفعل لهذه الميزة. احتفظنا بالنسخة المحفوظة دون تغيير.'}
    if copy.platform not in SUPPORTED:
        return {**result,'state':'UNSUPPORTED_PLATFORM','reason':'متطلبات هذه المنصة لم تكتمل؛ لا نقترح جاهزية نشر.'}
    if row.review_status!='APPROVED' or copy.source_fingerprint!=source_fingerprint(row):
        raise ValueError('اعتمد الأصل وراجع حداثة النسخة قبل طلب اقتراح.')
    if provider is None:return result
    # Only supplied source text and saved fields. No media bytes/URLs or metadata
    # secrets, and no model-generated visual claims from an unseen image.
    source={'text':row.content or str((row.artifact_metadata or {}).get('caption') or ''),'kind':row.kind}
    if not source['text'].strip():return {**result,'state':'INSUFFICIENT_SOURCE','reason':'لا يوجد نص مصدر كاف؛ لا نخترع وصفاً لوسيط لم نقرأه.'}
    try:
        proposed=validate_fields(await provider.suggest(platform=copy.platform,source=source,fields=deepcopy(current)))
        if proposed['alt_text']!=current['alt_text']:
            raise ValueError('النص البديل لا يولد من وسيط غير مشاهد.')
        if not proposed['description'].strip():raise ValueError('وصف الاقتراح فارغ.')
    except Exception:
        return {**result,'state':'PROVIDER_FAILED','reason':'تعذر الحصول على اقتراح صالح. بقيت الحقول المحفوظة كما هي، دون إعادة تلقائية.'}
    candidate=deepcopy(copy);candidate.fields=proposed
    checked=evaluate(row,candidate)
    return {**result,'state':'PROPOSED','fields':proposed,'reason':'اقتراح للمراجعة فقط، لم يطبق.',
        'field_status':checked['field_status'],'blockers':checked['blockers'],'warnings':checked['warnings']}


async def request_suggestion(session,uid,platform,version,fingerprint,provider=None):
    from sqlalchemy import select
    from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,CopySuggestionModel
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())).scalar_one_or_none()
    copy=await session.get(PlatformCopyModel,(uid,platform))
    if row is None or copy is None:raise ValueError('جهز نسخة المنصة أولاً.')
    if version!=copy.version or fingerprint!=source_fingerprint(row):raise ValueError('تغير الأصل أو النسخة؛ أعد تحميلها قبل الاقتراح.')
    result=await propose(row,copy,provider)
    if result['state']!='PROPOSED':return result
    from datetime import datetime,timezone
    record=CopySuggestionModel(artifact_id=uid,platform=platform,source_fingerprint=result['source_fingerprint'],copy_version=version,fields_digest=result['fields_digest'],fields=result['fields'],prompt_version=PROMPT_VERSION,state='PROPOSED',created_at=datetime.now(timezone.utc))
    session.add(record);await session.commit()
    return {**result,'suggestion_id':str(record.id)}


async def apply_suggestion(session,uid,platform,suggestion_id,version,fingerprint,confirmed):
    from datetime import datetime,timezone
    from sqlalchemy import select
    from app.infrastructure.database.models import ArtifactModel,PlatformCopyModel,CopySuggestionModel
    if confirmed is not True:raise ValueError('راجع الاقتراح وأكد تطبيقه صراحة.')
    row=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())).scalar_one_or_none()
    copy=await session.get(PlatformCopyModel,(uid,platform));proposal=await session.get(CopySuggestionModel,suggestion_id)
    if row is None or copy is None or proposal is None or proposal.artifact_id!=uid or proposal.platform!=platform or proposal.state!='PROPOSED':raise ValueError('الاقتراح غير متاح لهذه النسخة أو سبق تطبيقه.')
    if row.review_status!='APPROVED' or copy.source_fingerprint!=source_fingerprint(row) or proposal.source_fingerprint!=source_fingerprint(row) or fingerprint!=proposal.source_fingerprint or version!=copy.version or proposal.copy_version!=copy.version or proposal.fields_digest!=fields_digest(copy.fields):raise ValueError('تغير الأصل أو النسخة بعد الاقتراح. لم نستبدل تعديلاتك.')
    fields=validate_fields(proposal.fields)
    # Reuse existing mutation checks, but keep proposal and copy in one commit.
    from app.application.central_platform_copies import update_copy
    proposal.state='APPLIED';proposal.applied_at=datetime.now(timezone.utc)
    result=await update_copy(session,uid,platform,fields,version,fingerprint)
    return {**result,'suggestion_id':str(proposal.id),'suggestion_applied':True}
