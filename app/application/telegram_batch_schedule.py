"""Atomic draft schedule creation from an explicitly reviewed batch. Never activates."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.application.scheduling import validate_timezone
from app.application.telegram_batch_preview import preview_telegram_batch
from app.infrastructure.database.models import ArtifactModel, ScheduleModel, ScheduleItemModel


async def create_telegram_batch_schedule(session, *, artifact_ids, fingerprints, name, timezone_name, start_at, interval_minutes, destination, copy_versions=None, connection_id=None, commit=True):
    name = name.strip()
    if not name:
        raise ValueError('اكتب اسماً للخطة.')
    validate_timezone(timezone_name)
    if start_at.tzinfo is None or start_at.utcoffset() is None or start_at <= datetime.now(timezone.utc):
        raise ValueError('اختر وقت بداية مستقبلياً مع منطقة زمنية.')
    # Same selected originals share a lock boundary. The second concurrent
    # request sees the first draft reservation, not another eligible batch.
    await session.execute(select(ArtifactModel.id).where(ArtifactModel.id.in_(artifact_ids)).order_by(ArtifactModel.id).with_for_update())
    preview = await preview_telegram_batch(session, artifact_ids, connection_id=connection_id)
    connection_id=preview.get('connection_id')
    if destination != preview['destination']:
        raise ValueError('تغيرت الوجهة منذ المعاينة. أعد فحص الدفعة.')
    if preview['blocked_count']:
        raise ValueError('الدفعة محجوبة. حدّث المعاينة واقرأ أسباب المواد المحجوبة.')
    if any(fingerprints.get(item['artifact_id']) != item['source_fingerprint'] for item in preview['items']):
        raise ValueError('تغيرت المادة بعد المعاينة. أعد فحص الدفعة قبل حفظ الخطة.')
    if any((copy_versions or {}).get(item['artifact_id']) != item.get('copy_version') for item in preview['items']):
        raise ValueError('تغيرت نسخة Telegram بعد المعاينة. أعد الفحص.')
    binding={}
    if connection_id:
        from app.application.managed_connections import selected
        channel,_=await selected(session,connection_id)
        binding={'connection_id':str(channel.id),'bot_id':channel.details['bot_id'],'channel_label':channel.label}
    schedule = ScheduleModel(name=name, timezone=timezone_name, status='DRAFT', telegram_review={**binding,'destination':destination,'fingerprints':fingerprints,'copy_versions':{item['artifact_id']:item.get('copy_version') for item in preview['items']}})
    schedule.items = [ScheduleItemModel(artifact_id=uid, position=index+1, scheduled_at=start_at+timedelta(minutes=index*interval_minutes), status='PENDING') for index,uid in enumerate(artifact_ids)]
    session.add(schedule)
    if commit:await session.commit()
    else:await session.flush()
    return {'id':str(schedule.id),'name':name,'status':'DRAFT','timezone':timezone_name,'destination':preview['destination'],
            'items':[{'artifact_id':str(item.artifact_id),'scheduled_at':item.scheduled_at.isoformat()} for item in schedule.items]}


async def reviewed_batch_blocker(session, schedule):
    review = schedule.telegram_review
    if not review:
        return None
    import os
    from app.application.distribution_readiness import source_fingerprint
    from app.infrastructure.database.models import DistributionSelectionModel, PlatformCopyModel
    if review.get('connection_id'):
        from app.application.managed_connections import schedule_binding
        try:await schedule_binding(session,schedule)
        except ValueError as exc:return str(exc)
    elif review.get('destination') != os.getenv('TELEGRAM_DESTINATION_ID','').strip():
        return 'تغيرت وجهة Telegram منذ مراجعة الدفعة. أنشئ خطة جديدة بعد إعادة المعاينة.'
    for uid, fingerprint in review.get('fingerprints',{}).items():
        from uuid import UUID
        row=await session.get(ArtifactModel,UUID(uid))
        if row is None or source_fingerprint(row) != fingerprint:
            return 'تغير محتوى الدفعة بعد المراجعة. أعد المعاينة في خطة جديدة.'
        if 'copy_versions' in review:
            copy=await session.get(PlatformCopyModel,(UUID(uid),'telegram'))
            if (copy.version if copy else None) != review['copy_versions'].get(uid):
                return 'تغيرت نسخة Telegram بعد مراجعة الخطة. أعد المعاينة في خطة جديدة.'
        selection=await session.get(DistributionSelectionModel,UUID(uid))
        if selection and ('telegram' not in selection.platforms or selection.source_fingerprint != fingerprint):
            return 'تغير قرار توزيع Telegram للدفعة. أعد المعاينة في خطة جديدة.'
    return None
