"""Read-only, provenance-scoped results from live connector lifecycles.

No tokens, grants, approval evidence references or raw snapshots leave this view.
Dormant synthetic execution tables are deliberately excluded.
"""
from sqlalchemy import select, literal, union_all, exists, func, case
from app.infrastructure.database.models import (
    InstagramExecutionModel as Instagram, InstagramPublishDecisionModel as Decision,
    FacebookReelJobModel as Facebook, FacebookExecutionModel as Page,
)

EVIDENCE = r'^(owner-session|trusted-message):[A-Za-z0-9_.:-]{8,240}$'


def page_result_permalink():
    """Bind a Page result URL to its saved numeric Page and post, or withhold it."""
    page_identity = Page.page_id.bool_op('~')(r'^[0-9]{1,100}$') & Page.post_id.bool_op('~')(
        r'^[0-9]{1,100}_[0-9]{1,100}$') & (func.split_part(Page.post_id, '_', 1) == Page.page_id)
    # Only known numeric Page/post permalink forms can be bound to this row.
    # Unrecognized Facebook URLs remain withheld, even on the right domain.
    normalized_link = func.replace(Page.permalink, 'https://www.facebook.com/', 'https://facebook.com/')
    post_component = func.split_part(Page.post_id, '_', 2)
    post_path = literal('https://facebook.com/') + Page.page_id + '/posts/' + post_component
    permalink = literal('https://facebook.com/permalink.php?story_fbid=') + post_component + '&id=' + Page.page_id
    reversed_permalink = literal('https://facebook.com/permalink.php?id=') + Page.page_id + '&story_fbid=' + post_component
    page_link = page_identity & normalized_link.in_([post_path, post_path + '/', permalink, reversed_permalink])
    return case((page_link, Page.permalink), else_=None)


def results():
    approved = exists(select(Decision.id).where(
        Decision.execution_id == Instagram.id, Decision.evidence_ref.op('~')(EVIDENCE)))
    ig_link = Instagram.permalink.op('~')(r'^https://(www\.)?instagram\.com/(p|reel)/[A-Za-z0-9_-]+/?$')
    fb_link = Facebook.permalink.op('~')(r'^https://(www\.|m\.)?facebook\.com/(reel/[0-9]+/?|[0-9]+/videos/[0-9]+/?)$')
    ig = select(Instagram.id.label('id'), Instagram.artifact_id.label('artifact_id'),
        literal('INSTAGRAM_EXECUTION').label('record_type'), literal('instagram').label('platform'),
        Instagram.account_id.label('destination'), Instagram.caption.label('content'),
        Instagram.state.label('status'), Instagram.media_id.label('external_id'),
        Instagram.permalink.label('permalink'), Instagram.created_at.label('created_at'),
        Instagram.updated_at.label('updated_at'),
        ((Instagram.state == 'PUBLISHED') & Instagram.media_id.op('~')(r'^[0-9]+$') & ig_link).label('confirmed')
    ).where(approved, Instagram.connection_binding['login_mode'].astext == 'UNIFIED',
        Instagram.state.notin_(['DRAFT', 'CANCELLED']))
    fb = select(Facebook.id, Facebook.artifact_id, literal('FACEBOOK_REEL'), literal('facebook'),
        Facebook.snapshot['connection']['page_id'].astext, Facebook.snapshot['caption'].astext,
        Facebook.state, Facebook.remote_session['video_id'].astext, Facebook.permalink,
        Facebook.created_at, Facebook.updated_at,
        (Facebook.state == 'PUBLISHED') & Facebook.remote_session['video_id'].astext.op('~')(r'^[0-9]+$') & fb_link
    ).where(Facebook.evidence_ref.op('~')(EVIDENCE), Facebook.state.notin_(['DRAFT', 'CANCELLED']))
    # Only live-bound Page text/photo rows enter this historical projection.
    # Expiry does not erase prior publication. A known ID alone is not proof.
    page_identity = Page.page_id.bool_op('~')(r'^[0-9]{1,100}$') & Page.post_id.bool_op('~')(
        r'^[0-9]{1,100}_[0-9]{1,100}$') & (func.split_part(Page.post_id, '_', 1) == Page.page_id)
    page_confirmed = (Page.state == 'PUBLISHED_AT_LAST_CHECK') & page_identity
    page = select(Page.id, Page.artifact_id,
        case((Page.kind == 'IMAGE', 'FACEBOOK_PHOTO'), else_='FACEBOOK_TEXT'), literal('facebook'),
        Page.page_id, Page.message, Page.state, Page.post_id,
        page_result_permalink(), Page.created_at, Page.updated_at,
        page_confirmed).where(func.jsonb_typeof(Page.runtime_snapshot) == 'object',
        Page.runtime_snapshot['connection']['page_id'].astext == Page.page_id,
        Page.kind.in_(['TEXT', 'IMAGE']), Page.evidence_ref.bool_op('~')(EVIDENCE),
        Page.state.notin_(['DRAFT', 'CANCELLED']))
    return union_all(ig, fb, page).subquery('connector_results')


def confirmed_for(artifact_id):
    view = results()
    return exists(select(view.c.id).where(view.c.artifact_id == artifact_id, view.c.confirmed.is_(True)))


async def history(session, artifact_id):
    view = results()
    rows = (await session.execute(select(view).where(view.c.artifact_id == artifact_id)
        .order_by(view.c.created_at.desc(), view.c.id).limit(100))).mappings().all()
    return [dict(id=str(r['id']), record_type=r['record_type'], platform=r['platform'],
        destination=r['destination'], content=r['content'], status=r['status'],
        external_id=r['external_id'], permalink=r['permalink'] if r['confirmed'] else None,
        confirmed=r['confirmed'] is True, created_at=r['created_at'], updated_at=r['updated_at']) for r in rows]


def attention_for(artifact_id):
    view = results()
    return exists(select(view.c.id).where(view.c.artifact_id == artifact_id,
        view.c.status.notin_(['APPROVED', 'RETIRED_UNPUBLISHED']), view.c.confirmed.is_not(True)))
