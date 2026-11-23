"""Explicit draft and one-attempt execution for synthetic or supplied live points."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select, update
from app.infrastructure.database.models import ArtifactModel, PublicationModel, LiveLocationOperationModel
from app.domain.telegram_payloads import native_payload


async def current_live_location(session, publication_id, *, require_active=True, require_approved=True):
    publication = await session.get(PublicationModel, publication_id)
    if publication is None or publication.status != 'PUBLISHED' or publication.platform != 'telegram' or not publication.external_id or not publication.artifact_id:
        raise ValueError('A confirmed Telegram location publication is required.')
    artifact = await session.get(ArtifactModel, publication.artifact_id)
    native = (artifact.artifact_metadata or {}).get('telegram_native') if artifact else None
    if artifact is None or (require_approved and (artifact.status != 'AVAILABLE' or artifact.review_status != 'APPROVED')):
        raise ValueError('Live location source is no longer approved and available.')
    if not isinstance(native, dict) or native.get('type') != 'LIVE_LOCATION':
        raise ValueError('Publication is not a live location.')
    _, payload = native_payload(native)
    stopped = (await session.execute(select(LiveLocationOperationModel.id).where(LiveLocationOperationModel.publication_id == publication_id, LiveLocationOperationModel.action == 'STOP', LiveLocationOperationModel.status == 'COMPLETED'))).first()
    if publication.published_at is None:
        raise ValueError('Confirmed location publication timestamp is missing.')
    expires = publication.published_at + timedelta(seconds=payload['live_period'])
    if require_active and (stopped or datetime.now(timezone.utc) >= expires):
        raise ValueError('Live location is stopped or expired.')
    return publication, payload, expires


async def list_live_locations(session, artifact_id):
    rows = (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id == artifact_id, PublicationModel.status == 'PUBLISHED', PublicationModel.platform == 'telegram'))).scalars().all()
    result=[]
    for row in rows:
        pub, payload, expires = await current_live_location(session, row.id, require_active=False, require_approved=False)
        operations = (await session.execute(select(LiveLocationOperationModel).where(LiveLocationOperationModel.publication_id == row.id).order_by(LiveLocationOperationModel.created_at))).scalars().all()
        stopped=any(op.action=='STOP' and op.status=='COMPLETED' for op in operations)
        result.append({'publication_id':str(pub.id),'message_id':pub.external_id,'destination':pub.destination,'expires_at':expires,'active':not stopped and datetime.now(timezone.utc)<expires,'operations':[operation_payload(op) for op in operations]})
    return result


def operation_payload(row):
    return {'id':str(row.id),'publication_id':str(row.publication_id),'action':row.action,'payload':row.payload,'status':row.status,'error_message':row.error_message,'completed_at':row.completed_at}


async def create_operation(session, publication_id, *, action, latitude=None, longitude=None):
    if action not in {'UPDATE','STOP'}:raise ValueError('Unsupported live location action.')
    pub, native, expires=await current_live_location(session,publication_id, require_approved=action != 'STOP')
    if action=='UPDATE':
        _, payload=native_payload({'type':'LOCATION','latitude':latitude,'longitude':longitude})
    else:
        if latitude is not None or longitude is not None:raise ValueError('Stop does not accept coordinates.')
        payload={}
    # Serialize operations for this message, and refuse conflicting pending/uncertain work.
    await session.execute(select(PublicationModel.id).where(PublicationModel.id==publication_id).with_for_update())
    pending=(await session.execute(select(LiveLocationOperationModel).where(LiveLocationOperationModel.publication_id==publication_id,LiveLocationOperationModel.status.in_(['DRAFT','PROCESSING','UNCERTAIN'])))).scalars().all()
    for row in pending:
        if row.action==action and row.payload==payload:return operation_payload(row)
    if pending:raise ValueError('Review or settle the existing location operation before creating another.')
    row=LiveLocationOperationModel(publication_id=publication_id,action=action,payload=payload,status='DRAFT')
    session.add(row);await session.commit();await session.refresh(row)
    return operation_payload(row)


async def execute_operation(session, operation_id, publisher):
    row=await session.get(LiveLocationOperationModel,operation_id)
    if row is None or row.status!='DRAFT':raise ValueError('Location operation is not a reviewable DRAFT.')
    pub, _, _=await current_live_location(session,row.publication_id, require_approved=row.action != 'STOP')
    claimed=await session.execute(update(LiveLocationOperationModel).where(LiveLocationOperationModel.id==operation_id,LiveLocationOperationModel.status=='DRAFT').values(status='PROCESSING'))
    if claimed.rowcount!=1:raise ValueError('Location operation already claimed.')
    destination,message_id,action,payload=pub.destination,pub.external_id,row.action,dict(row.payload)
    await session.commit()
    try:
        await publisher.update_live_location(destination=destination,message_id=message_id,action=action,payload=payload)
    except Exception as exc:
        await session.execute(update(LiveLocationOperationModel).where(LiveLocationOperationModel.id==operation_id).values(status='UNCERTAIN',error_message=str(exc)))
    else:
        await session.execute(update(LiveLocationOperationModel).where(LiveLocationOperationModel.id==operation_id).values(status='COMPLETED',completed_at=datetime.now(timezone.utc),error_message=None))
    await session.commit();await session.refresh(row)
    return operation_payload(row)


async def cancel_operation(session, operation_id):
    result=await session.execute(update(LiveLocationOperationModel).where(LiveLocationOperationModel.id==operation_id,LiveLocationOperationModel.status=='DRAFT').values(status='CANCELLED'))
    if result.rowcount!=1:raise ValueError('Only an unexecuted draft operation can be cancelled.')
    await session.commit()
    return operation_payload(await session.get(LiveLocationOperationModel,operation_id))
