"""Read-only due-operation index. No raw snapshots, tokens or decision evidence."""
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, literal, union_all, func, cast, DateTime, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import InstagramDispatchModel as Dispatch, InstagramExecutionModel as Instagram, FacebookReelJobModel as Facebook, ArtifactModel, InstagramPublishDecisionModel as Decision, FacebookExecutionModel as FacebookText
from app.api.instagram_connections import owner, HEADERS
from app.application.connector_result_history import EVIDENCE

router=APIRouter(prefix='/api/platform-operations',tags=['platform-operations'])

@router.get('')
async def operations(request:Request,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),session:AsyncSession=Depends(get_session)):
    owner(request)
    ig=select(Instagram.id.label('id'),Instagram.artifact_id.label('artifact_id'),literal('instagram').label('platform'),Dispatch.due_at.label('due_at'),Decision.snapshot['timezone'].astext.label('timezone'),Dispatch.state.label('state'),Instagram.state.label('execution_state'),Instagram.connection_binding['username'].astext.label('destination'),Instagram.permalink.label('permalink'),Instagram.updated_at.label('updated_at')).join(Dispatch,Dispatch.execution_id==Instagram.id).join(Decision,Decision.id==Dispatch.decision_id).where(Instagram.connection_binding['login_mode'].astext=='UNIFIED',Decision.evidence_ref.op('~')(EVIDENCE))
    fb=select(Facebook.id,Facebook.artifact_id,literal('facebook'),cast(Facebook.snapshot['due_at'].astext,DateTime(timezone=True)),Facebook.snapshot['timezone'].astext,Facebook.state,Facebook.state,Facebook.snapshot['connection']['page_name'].astext,Facebook.permalink,Facebook.updated_at).where(Facebook.evidence_ref.op('~')(EVIDENCE))
    ft=select(FacebookText.id,FacebookText.artifact_id,case((FacebookText.kind=='IMAGE','facebook_photo'),else_='facebook_text'),FacebookText.due_at,FacebookText.runtime_snapshot['timezone'].astext,FacebookText.state,FacebookText.state,FacebookText.runtime_snapshot['connection']['page_name'].astext,FacebookText.permalink,FacebookText.updated_at).where(FacebookText.runtime_snapshot.is_not(None),FacebookText.evidence_ref.op('~')(EVIDENCE))
    view=union_all(ig,fb,ft).subquery()
    total=await session.scalar(select(func.count()).select_from(view))
    grouped=(await session.execute(select(view.c.state,func.count()).group_by(view.c.state))).all()
    counts=dict(waiting=0,published=0,attention=0,total=total)
    for state,n in grouped:
        if state in {'APPROVED','PENDING','WAITING_MEDIA','CLAIMED','PROCESSING','POST_ID_KNOWN','RESULT_KNOWN','SENDING','FINISH_ACCEPTED'}:counts['waiting']+=n
        elif state in {'PUBLISHED','PUBLISHED_AT_LAST_CHECK'}:counts['published']+=n
        elif state in {'BLOCKED','FAILED','RESULT_CHANGED','OUTCOME_UNKNOWN','RECONCILE_ONLY','NOT_CONFIRMED_PUBLISHED'}:counts['attention']+=n
    rows=(await session.execute(select(view,ArtifactModel.artifact_metadata.label('metadata'),ArtifactModel.content.label('content')).join(ArtifactModel,ArtifactModel.id==view.c.artifact_id).order_by(view.c.updated_at.desc(),view.c.id).offset(offset).limit(limit))).mappings().all()
    items=[]
    import re
    for r in rows:
        link=r['permalink'] or ''
        pattern=r'^https://(www\.)?instagram\.com/(p|reel)/[A-Za-z0-9_-]+/?$' if r['platform']=='instagram' else r'^https://(www\.|m\.)?facebook\.com/(reel/[0-9]+/?|[0-9]+/videos/[0-9]+/?)$'
        if r['platform'] in {'facebook_text','facebook_photo'}:pattern=r'^https://(www\.)?facebook\.com/[^\s]+$'
        items.append(dict(id=str(r['id']),artifact_id=str(r['artifact_id']),platform=r['platform'],due_at=r['due_at'].isoformat() if r['due_at'] else None,timezone=r['timezone'],state=r['state'],execution_state=r['execution_state'],destination=r['destination'],title=str((r['metadata'] or {}).get('title') or (r['metadata'] or {}).get('caption') or r['content'] or 'مادة '+str(r['artifact_id'])[:8]).split('\n')[0][:120],permalink=link if r['execution_state'] in {'PUBLISHED','PUBLISHED_AT_LAST_CHECK'} and re.fullmatch(pattern,link) else None))
    return JSONResponse(dict(items=items,total=total,limit=limit,offset=offset,counts=counts),headers=HEADERS)
