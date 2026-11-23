from app.domain.telegram_copy import telegram_publish_text
"""Read-only batch preflight for approved generic Telegram originals."""
import os
from sqlalchemy import select
from app.application.distribution_readiness import source_fingerprint
from app.application.telegram_copy_readiness import telegram_copy_blockers
from app.infrastructure.database.models import ArtifactModel, DistributionSelectionModel, PublicationModel, ScheduleItemModel, ScheduleModel, PlatformCopyModel


async def preview_telegram_batch(session, artifact_ids):
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError('تحديد مكرر؛ اختر كل مادة مرة واحدة.')
    rows = (await session.execute(select(ArtifactModel).where(ArtifactModel.id.in_(artifact_ids)))).scalars().all()
    found = {row.id: row for row in rows}
    selections = {row.artifact_id: row for row in (await session.execute(select(DistributionSelectionModel).where(DistributionSelectionModel.artifact_id.in_(artifact_ids)))).scalars().all()}
    publications = (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id.in_(artifact_ids), PublicationModel.platform == 'telegram'))).scalars().all()
    schedules = (await session.execute(select(ScheduleItemModel.artifact_id, ScheduleModel.name, ScheduleModel.status, ScheduleItemModel.status).join(ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id).where(ScheduleItemModel.artifact_id.in_(artifact_ids), ScheduleModel.status.in_(['DRAFT','ACTIVE','PAUSED']), ScheduleItemModel.status.in_(['PENDING','PROCESSING','PUBLISHED'])))).all()
    copies = {copy.artifact_id:copy for copy in (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id.in_(artifact_ids),PlatformCopyModel.platform=='telegram'))).scalars().all()}
    destination = os.getenv('TELEGRAM_DESTINATION_ID', '').strip()
    items = []
    for uid in artifact_ids:
        row = found.get(uid)
        blockers = []
        if row is None:
            items.append({'artifact_id':str(uid),'title':'مادة غير موجودة','content':'','ready':False,'blockers':['تعذر العثور على المادة.'],'publications':[],'schedules':[]})
            continue
        meta = row.artifact_metadata or {}
        if row.kind == 'POST' or meta.get('source_type') == 'PLATFORM_VARIANT':
            blockers.append('اختر المادة الأصلية من مسار المخرجات.')
        if row.review_status != 'APPROVED' or row.status != 'AVAILABLE':
            blockers.append('اعتمد المادة الأصلية وأتح توفرها قبل التجهيز.')
        copy=copies.get(uid)
        text=telegram_publish_text(row)
        if copy:
            from app.application.central_platform_copies import evaluate
            blockers.extend(evaluate(row,copy)['blockers'])
            text=copy.fields['description']
        else:
            blockers.extend(telegram_copy_blockers(row))
        selection = selections.get(uid)
        if selection is not None:
            if selection.source_fingerprint != source_fingerprint(row):
                blockers.append('تغيرت المادة منذ اختيار وجهاتها؛ حدّث اختيار التوزيع.')
            if 'telegram' not in selection.platforms:
                blockers.append('Telegram مستبعد من الوجهات المحفوظة لهذه المادة.')
        pubs = [p for p in publications if p.artifact_id == uid]
        if any(p.status in {'PUBLISHED','PUBLISHING','READY'} for p in pubs):
            blockers.append('للمادة نشر سابق أو عملية غير محسومة؛ راجع السجل بدلاً من إعادة الإرسال.')
        planned = [{'name':name,'schedule_status':status,'item_status':item_status} for artifact_id,name,status,item_status in schedules if artifact_id == uid]
        if planned:
            blockers.append('المادة مرتبطة بجدول قائم؛ افتح الجدول لتعديله بدلاً من إنشاء نسخة.')
        if not destination:
            blockers.append('لم تُضبط وجهة Telegram في الخادم.')
        items.append({'artifact_id':str(uid),'title':str(meta.get('title') or meta.get('original_filename') or row.kind),'kind':row.kind,
                      'content':text,'copy_version':copy.version if copy else None,
                      'source_fingerprint':source_fingerprint(row),'ready':not blockers,'blockers':blockers,
                      'publications':[{'id':str(p.id),'status':p.status,'external_ids':p.external_ids or ([p.external_id] if p.external_id else [])} for p in pubs], 'schedules':planned})
    return {'destination':destination or None,'items':items,'ready_count':sum(item['ready'] for item in items),
            'blocked_count':sum(not item['ready'] for item in items),'read_only':True,'execution_authorized':False,
            'caveat':'فحص نصي أولي. فحص بايتات الوسائط وصلاحية الحساب النهائية عند التنفيذ، ولا يمنح هذا الفحص إذن نشر.'}
