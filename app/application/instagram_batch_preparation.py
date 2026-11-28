"""Unregistered private atomic preparation. No decisions, dispatches or grants.

Never loop through individually committing staging helpers. This coordinator
owns one fresh transaction and inserts all exact child rows or none.
"""
from datetime import datetime,timezone
from uuid import UUID
from zoneinfo import ZoneInfo
import re
from sqlalchemy import select,text
from app.infrastructure.database.models import (InstagramPrivateBatchReviewModel as BatchReview,
    InstagramPrivateBatchPreparationModel as Preparation, InstagramPlanDraftModel as Review,
    InstagramExecutionModel as Job,ArtifactModel as Artifact,PlatformCopyModel as Copy,
    DistributionSelectionModel as Selection,InstagramConnectionModel as Connection,
    PlatformMediaInspectionModel as Inspection)
from app.application import instagram_batch_review as private,instagram_plan_review as review,instagram_oauth as oauth
from app.application.instagram_media_pin import inspection_for_copy


def describe(row):
    return dict(id=str(row.id),review_id=str(row.review_id),snapshot_hash=row.snapshot_hash,
        items=row.items,created_at=row.created_at.isoformat(),execution_enabled=False,
        scheduled=False,approval_recorded=False,media_exposure_enabled=False)

async def prepare(session,review_id,*,snapshot_hash,request_key):
    if session.in_transaction():raise ValueError('Fresh transaction required for complete private preparation')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{8,100}',request_key):raise ValueError('Stable request key required')
    async with session.begin():
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(606035)')):raise ValueError('Another private preparation is in progress')
        prior=await session.scalar(select(Preparation).where(Preparation.request_key==request_key).with_for_update(nowait=True))
        if prior:
            if prior.review_id!=review_id or prior.snapshot_hash!=snapshot_hash:raise ValueError('Request key belongs to another exact saved review')
            return describe(prior)
        batch=await session.scalar(select(BatchReview).where(BatchReview.id==review_id).with_for_update(nowait=True))
        if not batch or batch.state!='DRAFT' or batch.snapshot_hash!=snapshot_hash:raise ValueError('Exact live private review required')
        existing=await session.scalar(select(Preparation).where(Preparation.review_id==review_id))
        if existing:raise ValueError('This review already owns preparation; recover its original receipt, never make another')
        ids=sorted(UUID(i['artifact_id']) for i in batch.snapshot['items'])
        # Same source/copy order as individual editors; NOWAIT prevents inversions.
        for model,column in [(Artifact,Artifact.id),(Copy,Copy.artifact_id),(Selection,Selection.artifact_id)]:
            await session.execute(select(model).where(column.in_(ids)).order_by(column).with_for_update(nowait=True).execution_options(populate_existing=True))
        if not await session.scalar(text('SELECT pg_try_advisory_xact_lock(606024)')):raise ValueError('Account lifecycle changed')
        conn=await session.scalar(select(Connection).where(Connection.id==1).with_for_update(nowait=True).execution_options(populate_existing=True))
        inspection_ids=[UUID(i['inspection']['id']) for i in batch.snapshot['items'] if i.get('inspection')]
        await session.execute(select(Inspection).where(Inspection.id.in_(inspection_ids)).order_by(Inspection.id).with_for_update(nowait=True).execution_options(populate_existing=True))
        # Pin currently visible job rows as well. A future activation must repeat
        # conflict checks; preparation alone never reserves permission to publish.
        await session.execute(select(Job).where(Job.artifact_id.in_(ids)).order_by(Job.id).with_for_update(nowait=True).execution_options(populate_existing=True))
        values=[dict(artifact_id=i['artifact_id'],due_at=datetime.fromisoformat(i['due_at']),timezone=i['timezone'],share_to_feed=i['share_to_feed']) for i in batch.snapshot['items']]
        current=await private.preview(session,values)
        if current['preview_hash']!=snapshot_hash or not current['can_save_draft'] or current['blocked_count']:raise ValueError('Complete saved review is stale or blocked; prepare nothing')
        config=await oauth.configuration_for(session,True)
        if not conn:raise ValueError('Selected Unified connection required')
        pending=[]
        for item in current['items']:
            uid=UUID(item['artifact_id'])
            inspection=await inspection_for_copy(session,uid,UUID(item['inspection']['id']),fingerprint=item['source_fingerprint'],copy_version=item['copy_version'])
            p=await review.preview(session,uid,share_to_feed=item['share_to_feed'],planned_at=datetime.fromisoformat(item['due_at']).astimezone(ZoneInfo(item['timezone'])),timezone_name=item['timezone'])
            if p['blockers'] or p['source_fingerprint']!=item['source_fingerprint'] or p['copy_version']!=item['copy_version'] or p['inspection']['id']!=str(inspection.id):raise ValueError('One exact child changed; prepare nothing')
            pending.append((item,p,inspection))
        receipt=Preparation(review_id=review_id,request_key=request_key,snapshot_hash=snapshot_hash,items=[],created_at=datetime.now(timezone.utc))
        session.add(receipt);await session.flush()
        # Validation of every child precedes the first private child insertion.
        for item,p,inspection in pending:
            rid=Review(artifact_id=UUID(item['artifact_id']),snapshot_hash=p['preview_hash'],snapshot=p,state='DRAFT')
            session.add(rid);await session.flush()
            job=Job(artifact_id=rid.artifact_id,inspection_id=inspection.id,account_id=item['account']['account_id'],
                source_fingerprint=item['source_fingerprint'],copy_version=item['copy_version'],media_sha256=inspection.sha256,
                kind=item['kind'],caption=item['caption'],alt_text=item['alt_text'],share_to_feed=item['share_to_feed'],state='DRAFT',
                created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc),connection_binding=dict(
                    login_mode='PRIVATE_BATCH_UNIFIED',config_hash=config['fingerprint'],connected_at=conn.connected_at.isoformat(),
                    client_business_id=conn.client_business_id,token_hash=oauth.digest(conn.token_ciphertext),username=conn.username,
                    review_id=str(rid.id),review_hash=rid.snapshot_hash,private_batch_preparation_id=str(receipt.id)))
            session.add(job);await session.flush()
            receipt.items=[*receipt.items,dict(artifact_id=item['artifact_id'],review_id=str(rid.id),execution_id=str(job.id),
                due_at=item['due_at'],timezone=item['timezone'],share_to_feed=item['share_to_feed'])]
        # No live work is inserted. Future exact approval must recheck bytes,
        # account, all conflicts and only exclude these exact owned draft IDs.
        return describe(receipt)
