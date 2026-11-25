"""Read-only due-operation index. No raw snapshots, tokens or decision evidence."""
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi.responses import JSONResponse
from sqlalchemy import select, literal, union_all, func, cast, DateTime, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import InstagramDispatchModel as Dispatch, InstagramExecutionModel as Instagram, FacebookReelJobModel as Facebook, ArtifactModel, InstagramPublishDecisionModel as Decision, FacebookExecutionModel as FacebookText
from app.api.instagram_connections import owner, HEADERS
from app.application.connector_result_history import EVIDENCE

WAITING={'APPROVED','PENDING','WAITING_MEDIA','CLAIMED','PROCESSING','POST_ID_KNOWN','RESULT_KNOWN','SENDING','FINISH_ACCEPTED'}
PUBLISHED={'PUBLISHED','PUBLISHED_AT_LAST_CHECK'}
ATTENTION={'BLOCKED','FAILED','RESULT_CHANGED','OUTCOME_UNKNOWN','RECONCILE_ONLY','NOT_CONFIRMED_PUBLISHED'}

router=APIRouter(prefix='/api/platform-operations',tags=['platform-operations'])

@router.get('')
async def operations(request:Request,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),date:str|None=Query(None,pattern=r"^\d{4}-\d{2}-\d{2}$"),timezone_name:str=Query("UTC",alias="timezone"),platform:Literal['all','instagram','facebook','facebook_text','facebook_photo']=Query('all'),state_group:Literal['all','waiting','published','attention','other']=Query('all'),session:AsyncSession=Depends(get_session)):
    owner(request)
    ig=select(Instagram.id.label('id'),Instagram.artifact_id.label('artifact_id'),literal('instagram').label('platform'),Dispatch.due_at.label('due_at'),Decision.snapshot['timezone'].astext.label('timezone'),Dispatch.state.label('state'),Instagram.state.label('execution_state'),Instagram.connection_binding['username'].astext.label('destination'),Instagram.permalink.label('permalink'),Instagram.updated_at.label('updated_at')).join(Dispatch,Dispatch.execution_id==Instagram.id).join(Decision,Decision.id==Dispatch.decision_id).where(Instagram.connection_binding['login_mode'].astext=='UNIFIED',Decision.evidence_ref.op('~')(EVIDENCE))
    fb=select(Facebook.id,Facebook.artifact_id,literal('facebook'),cast(Facebook.snapshot['due_at'].astext,DateTime(timezone=True)),Facebook.snapshot['timezone'].astext,Facebook.state,Facebook.state,Facebook.snapshot['connection']['page_name'].astext,Facebook.permalink,Facebook.updated_at).where(Facebook.evidence_ref.op('~')(EVIDENCE))
    ft=select(FacebookText.id,FacebookText.artifact_id,case((FacebookText.kind=='IMAGE','facebook_photo'),else_='facebook_text'),FacebookText.due_at,FacebookText.runtime_snapshot['timezone'].astext,FacebookText.state,FacebookText.state,FacebookText.runtime_snapshot['connection']['page_name'].astext,FacebookText.permalink,FacebookText.updated_at).where(FacebookText.runtime_snapshot.is_not(None),FacebookText.evidence_ref.op('~')(EVIDENCE))
    view=union_all(ig,fb,ft).subquery()
    if date is not None:
        try:
            zone=ZoneInfo(timezone_name)
            local=datetime.strptime(date,'%Y-%m-%d').date()
            start=datetime.combine(local,datetime.min.time(),tzinfo=zone)
            end=start+timedelta(days=1)
        except (ValueError,ZoneInfoNotFoundError) as exc:
            raise HTTPException(400,'Invalid date or timezone.') from exc
        view=select(view).where(view.c.due_at>=start.astimezone(timezone.utc),view.c.due_at<end.astimezone(timezone.utc)).subquery()
    if platform!='all':view=select(view).where(view.c.platform==platform).subquery()
    if state_group!='all':
        states={'waiting':WAITING,'published':PUBLISHED,'attention':ATTENTION}
        condition=view.c.state.not_in(WAITING|PUBLISHED|ATTENTION) if state_group=='other' else view.c.state.in_(states[state_group])
        view=select(view).where(condition).subquery()
    total=await session.scalar(select(func.count()).select_from(view))
    grouped=(await session.execute(select(view.c.state,func.count()).group_by(view.c.state))).all()
    counts=dict(waiting=0,published=0,attention=0,total=total)
    for state,n in grouped:
        if state in WAITING:counts['waiting']+=n
        elif state in PUBLISHED:counts['published']+=n
        elif state in ATTENTION:counts['attention']+=n
    rows=(await session.execute(select(view,ArtifactModel.artifact_metadata.label('metadata'),ArtifactModel.content.label('content')).join(ArtifactModel,ArtifactModel.id==view.c.artifact_id).order_by(*([view.c.due_at,view.c.id] if date is not None else [view.c.updated_at.desc(),view.c.id])).offset(offset).limit(limit))).mappings().all()
    items=[]
    import re
    for r in rows:
        link=r['permalink'] or ''
        pattern=r'^https://(www\.)?instagram\.com/(p|reel)/[A-Za-z0-9_-]+/?$' if r['platform']=='instagram' else r'^https://(www\.|m\.)?facebook\.com/(reel/[0-9]+/?|[0-9]+/videos/[0-9]+/?)$'
        if r['platform'] in {'facebook_text','facebook_photo'}:pattern=r'^https://(www\.)?facebook\.com/[^\s]+$'
        items.append(dict(id=str(r['id']),artifact_id=str(r['artifact_id']),platform=r['platform'],due_at=r['due_at'].isoformat() if r['due_at'] else None,timezone=r['timezone'],state=r['state'],execution_state=r['execution_state'],destination=r['destination'],title=str((r['metadata'] or {}).get('title') or (r['metadata'] or {}).get('caption') or r['content'] or 'مادة '+str(r['artifact_id'])[:8]).split('\n')[0][:120],permalink=link if r['execution_state'] in {'PUBLISHED','PUBLISHED_AT_LAST_CHECK'} and re.fullmatch(pattern,link) else None))
    return JSONResponse(dict(items=items,total=total,limit=limit,offset=offset,counts=counts,platform=platform,state_group=state_group,date=date,timezone=timezone_name if date else None),headers=HEADERS)
