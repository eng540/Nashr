"""Synthetic test journey only. No route, scheduler registration, token or HTTP client.

This module cannot accept a real provider or create a media URL. A synthetic
confirmation is test input, never an owner grant that production may consume.
"""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from app.application import instagram_execution as execution
from app.application.instagram_plan_review import describe_draft
from app.infrastructure.database.models import InstagramPlanDraftModel
from app.adapters.publishing.instagram import ContainerState, InstagramProviderError


class SyntheticProvider:
    def __init__(self, account_id, outcome):
        self.account_id=account_id;self.outcome=outcome;self.calls=[]
    async def create_container(self, **kwargs):
        self.calls.append('create')
        if self.outcome=='create_unknown':raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN',outcome_unknown=True)
        return '900000000001'
    async def publish_container(self, container_id):
        self.calls.append('publish')
        if self.outcome=='publish_unknown':raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN',outcome_unknown=True)
        return '900000000002'
    async def published_media(self, media_id):
        self.calls.append('reconcile')
        return {'media_id':media_id,'account_id':self.account_id,'permalink':'https://www.instagram.com/p/synthetic-test-only/'}
    async def container_status(self, container_id):
        self.calls.append('status');return ContainerState(container_id,'PUBLISHED')


async def simulate_due_review(session, draft_id, *, reviewed_hash, due_at, outcome='success'):
    """Used only with seeded synthetic accounts/media in integration tests.

    Due time is injected so tests need no waiting. No production authority is
    written, no saved connection token is opened and no URL is made accessible.
    """
    if outcome not in {'success','create_unknown','publish_unknown'}:raise ValueError('Unsupported synthetic outcome')
    draft=(await session.execute(select(InstagramPlanDraftModel).where(InstagramPlanDraftModel.id==UUID(str(draft_id))).with_for_update())).scalar_one_or_none()
    if draft is None or draft.snapshot_hash!=reviewed_hash:raise ValueError('Review decision does not match this draft')
    description=await describe_draft(session,draft);snapshot=draft.snapshot
    if draft.state!='DRAFT' or description['stale'] or snapshot['blockers']:raise ValueError('Review is stale or blocked')
    timing=snapshot.get('timing_intent')
    if not timing or due_at.tzinfo is None or datetime.fromisoformat(timing['planned_at'])>due_at.astimezone(timezone.utc):raise ValueError('Proposed review time is not due')
    if not snapshot['account'] or not snapshot['inspection']:raise ValueError('Selected account and measured media required')
    draft.state='SIMULATING';await session.commit()
    provider=SyntheticProvider(snapshot['account']['account_id'],outcome)
    job=await execution.prepare(session,draft.artifact_id,account_id=provider.account_id,
        media_sha256=snapshot['inspection']['sha256'],copy_version=snapshot['copy_version'],
        fingerprint=snapshot['source_fingerprint'],inspection_id=UUID(snapshot['inspection']['id']),share_to_feed=snapshot['share_to_feed'])
    # Deliberately unresolvable URL, consumed only by the in-memory fake above.
    job=await execution.create_container(session,job.id,provider=provider,media_url='https://synthetic.invalid/no-media',media_sha256=job.media_sha256,authorized=True)
    if job.state=='CONTAINER_CREATED':job=await execution.publish(session,job.id,provider=provider,media_sha256=job.media_sha256,authorized=True)
    if job.state in {'PUBLISHED_ID_KNOWN','PUBLISH_UNKNOWN'}:job=await execution.reconcile(session,job.id,provider=provider)
    return {'execution_id':str(job.id),'state':job.state,'calls':provider.calls,'synthetic_only':True,'owner_approval_recorded':False,'external_requests':0,'media_exposed':False}
