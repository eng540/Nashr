"""Dormant private-child provenance reader. Not execution or Stop authority.

Only the persisted parent receipt selects children. No client child IDs, control
creation, decision/grant insertion, runtime bridge or provider access exists.
Locks last only for this read transaction; output is not an activation token.
"""
from uuid import UUID
from datetime import datetime
from sqlalchemy import select
from app.infrastructure.database.models import (
    InstagramPrivateBatchPreparationModel as Preparation,
    InstagramPrivateBatchReviewModel as Batch,
    InstagramPlanDraftModel as Review, InstagramExecutionModel as Job)
from app.application.instagram_plan_review import fingerprint


def _ids(rows, key):
    values = [UUID(str(row[key])) for row in rows]
    if len(set(values)) != len(values):
        raise ValueError('Duplicate private child identity')
    return values


def _digest(snapshot, *, batch=False):
    if batch:
        return fingerprint({k: snapshot[k] for k in ('items', 'connection_binding_digest')})
    return fingerprint({k: v for k, v in snapshot.items()
                        if k not in {'preview_hash', 'can_save_draft', 'caveat'}})


async def _resolve(session, preparation_id, *, review_id, snapshot_hash):
    """Read exact private DRAFT ownership, never fresh execution eligibility."""
    if session.in_transaction():
        raise ValueError('Fresh owned provenance transaction required')
    async with session.begin():
        parent = await session.scalar(select(Batch).where(Batch.id == review_id)
            .with_for_update(nowait=True).execution_options(populate_existing=True))
        receipt = await session.scalar(select(Preparation).where(Preparation.id == preparation_id)
            .with_for_update(nowait=True).execution_options(populate_existing=True))
        if (not parent or not receipt or parent.state != 'DRAFT'
                or receipt.review_id != parent.id or parent.snapshot_hash != snapshot_hash
                or receipt.snapshot_hash != snapshot_hash or _digest(parent.snapshot, batch=True) != snapshot_hash):
            raise ValueError('Exact live private parent and preparation required')
        entries = receipt.items
        snapshots = parent.snapshot['items']
        if not 1 <= len(entries) <= 20 or len(entries) != len(snapshots):
            raise ValueError('Complete bounded private child set required')
        artifacts = _ids(entries, 'artifact_id')
        jobs = _ids(entries, 'execution_id')
        reviews = _ids(entries, 'review_id')
        # Lock in stable order, NOWAIT on inversions with existing editors.
        children = list((await session.scalars(select(Job).where(Job.id.in_(jobs))
            .order_by(Job.id).with_for_update(nowait=True).execution_options(populate_existing=True))).all())
        drafts = list((await session.scalars(select(Review).where(Review.id.in_(reviews))
            .order_by(Review.id).with_for_update(nowait=True).execution_options(populate_existing=True))).all())
        if len(children) != len(entries) or len(drafts) != len(entries):
            raise ValueError('Missing private child')
        by_job = {j.id: j for j in children}
        by_review = {r.id: r for r in drafts}
        owned_ids = set((await session.scalars(select(Job.id).where(
            Job.connection_binding['private_batch_preparation_id'].astext == str(receipt.id))
            .order_by(Job.id).with_for_update(nowait=True))).all())
        if owned_ids != set(jobs):
            raise ValueError('Receipt does not name its complete owned private child set')
        result = []
        for n, (entry, saved) in enumerate(zip(entries, snapshots)):
            job, draft = by_job[jobs[n]], by_review[reviews[n]]
            binding = job.connection_binding or {}
            private = draft.snapshot
            timing = private.get('timing_intent') or {}
            same = (str(artifacts[n]) == saved['artifact_id']
                and job.artifact_id == artifacts[n] == draft.artifact_id
                and job.state == draft.state == 'DRAFT'
                and not any((job.container_id, job.media_id, job.permalink))
                and binding.get('login_mode') == 'PRIVATE_BATCH_UNIFIED'
                and binding.get('private_batch_preparation_id') == str(receipt.id)
                and fingerprint([binding.get('config_hash'),
                    datetime.fromisoformat(binding['connected_at']),
                    binding.get('client_business_id'), binding.get('token_hash')])
                    == parent.snapshot['connection_binding_digest']
                and binding.get('review_id') == str(draft.id)
                and binding.get('review_hash') == draft.snapshot_hash == _digest(private)
                and private.get('preview_hash') == draft.snapshot_hash
                and timing.get('planned_at') == entry['due_at'] == saved['due_at']
                and timing.get('timezone') == entry['timezone'] == saved['timezone']
                and job.share_to_feed == entry['share_to_feed'] == saved['share_to_feed'] == private['share_to_feed']
                and job.account_id == saved['account']['account_id'] == private['account']['account_id']
                and binding.get('username') == saved['account']['username'] == private['account']['username']
                and str(job.inspection_id) == saved['inspection']['id'] == private['inspection']['id']
                and job.media_sha256 == saved['inspection']['sha256'] == private['inspection']['sha256'])
            for key in ('source_fingerprint', 'copy_version', 'caption', 'alt_text', 'kind'):
                same = same and getattr(job, key) == saved[key] == private[key]
            if not same:
                raise ValueError('Private child provenance differs from its exact saved parent')
            result.append(dict(entry))
        return dict(preparation_id=str(receipt.id), review_id=str(parent.id),
            snapshot_hash=snapshot_hash, items=result, execution_enabled=False,
            currentness_verified=False, stop_enabled=False,
            caveat='Private ownership only. Locks released on return. No execution or Stop permission.')


async def resolve(session, preparation_id, *, review_id, snapshot_hash):
    try:
        return await _resolve(session, preparation_id, review_id=review_id, snapshot_hash=snapshot_hash)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError('Malformed private provenance; no authority resolved') from exc
