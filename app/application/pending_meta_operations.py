"""Read-only index of saved, unclaimed Meta schedules.

This describes recorded intent, never readiness or permission to execute.
Runtime still rechecks exact content, account, consent and media at dispatch.
"""
from sqlalchemy import select, literal, union_all, exists, func, cast, DateTime
from app.infrastructure.database.models import (InstagramExecutionModel as IG,
    InstagramDispatchModel as Dispatch, InstagramPublishDecisionModel as Decision,
    FacebookReelJobModel as FB, FacebookExecutionModel as FT)
from app.application.connector_result_history import EVIDENCE


def pending_operations():
    ig = select(IG.id.label('id'), IG.artifact_id.label('artifact_id'),
        literal('instagram').label('platform'), Dispatch.due_at.label('due_at')).join(
        Dispatch, Dispatch.execution_id == IG.id).join(Decision, Decision.id == Dispatch.decision_id).where(
        IG.state == 'DRAFT', IG.connection_binding['login_mode'].astext == 'UNIFIED',
        Dispatch.state == 'PENDING', Decision.execution_id == IG.id,
        Decision.state == 'APPROVED', Decision.expires_at > func.now(),
        Decision.evidence_ref.op('~')(EVIDENCE))
    fb = select(FB.id, FB.artifact_id, literal('facebook'),
        cast(FB.snapshot['due_at'].astext, DateTime(timezone=True))).where(
        FB.state == 'APPROVED', FB.approved_until > func.now(),
        FB.snapshot['due_at'].astext.is_not(None), FB.evidence_ref.op('~')(EVIDENCE))
    from sqlalchemy import case
    ft = select(FT.id, FT.artifact_id,
        case((FT.kind == 'IMAGE', 'facebook_photo'), else_='facebook_text'), FT.due_at).where(
        FT.state == 'APPROVED', FT.approved_until > func.now(), FT.due_at.is_not(None),
        func.jsonb_typeof(FT.runtime_snapshot) == 'object', FT.kind.in_(['TEXT', 'IMAGE']), FT.evidence_ref.op('~')(EVIDENCE))
    return union_all(ig, fb, ft).subquery('pending_meta_operations')


def planned_for(artifact_id):
    view = pending_operations()
    return exists(select(view.c.id).where(view.c.artifact_id == artifact_id))
