"""Read-only cross-model operations queue. Execution contracts stay separate."""
from sqlalchemy.dialects.postgresql import JSONB
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, union_all, literal, func, cast, String, exists, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import (ArtifactModel, PostModel, KnowledgeUnitModel,
    PublicationModel, ScheduleItemModel, ScheduleModel, DistributionSelectionModel, PlatformCopyModel, ArtifactOrganizationModel)

router = APIRouter(prefix='/api/publishing-queue', tags=['publishing-queue'])


def _confirmed(publication):
    return (publication.status == 'PUBLISHED') & or_(
        func.length(func.trim(func.coalesce(publication.external_id, ''))) > 0,
        func.jsonb_array_length(func.coalesce(publication.external_ids, literal('[]').cast(JSONB))) > 0)


def _unresolved_publication_failure(reference, content_type):
    failed = aliased(PublicationModel)
    recovered = aliased(PublicationModel)
    failed_ref = failed.post_id if content_type == 'POST' else failed.artifact_id
    recovered_ref = recovered.post_id if content_type == 'POST' else recovered.artifact_id
    # Only a later confirmed result for the exact same platform, destination and
    # connection supersedes this failure. Another channel's success proves nothing.
    recovery = exists(select(recovered.id).where(recovered_ref == failed_ref,
        recovered.platform == failed.platform, recovered.destination == failed.destination,
        recovered.content == failed.content,
        recovered.connection_id.is_not_distinct_from(failed.connection_id), _confirmed(recovered),
        func.coalesce(recovered.published_at, recovered.created_at) > failed.created_at)).correlate(failed)
    return exists(select(failed.id).where(failed_ref == reference,
        failed.status == 'FAILED', ~recovery))


def _failed_item():
    # A scheduler item can retain FAILED while result recovery records delivery.
    # Only its linked confirmed publication proves recovery, never an unrelated send.
    recovered = exists(select(PublicationModel.id).where(
        PublicationModel.id == ScheduleItemModel.publication_id,
        PublicationModel.post_id.is_not_distinct_from(ScheduleItemModel.post_id),
        PublicationModel.artifact_id.is_not_distinct_from(ScheduleItemModel.artifact_id),
        _confirmed(PublicationModel))).correlate(ScheduleItemModel)
    return (ScheduleItemModel.status == 'FAILED') & ~recovered


def _state(reference, content_type):
    pub_ref = PublicationModel.post_id if content_type == 'POST' else PublicationModel.artifact_id
    item_ref = ScheduleItemModel.post_id if content_type == 'POST' else ScheduleItemModel.artifact_id
    published = exists(select(PublicationModel.id).where(pub_ref == reference, _confirmed(PublicationModel)))
    planned = exists(select(ScheduleItemModel.id).join(ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id)
        .where(item_ref == reference, ScheduleModel.status.in_(['DRAFT','ACTIVE','PAUSED']), ScheduleItemModel.status.in_(['PENDING','PROCESSING'])))
    failed = or_(_unresolved_publication_failure(reference, content_type),
        exists(select(ScheduleItemModel.id).join(ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id)
            .where(item_ref == reference, _failed_item(), ScheduleModel.status != 'CANCELLED')))
    return case((failed, 'ATTENTION'), (planned, 'PLANNED'), (published, 'PUBLISHED'), else_='APPROVED')


@router.get('')
async def publishing_queue(q: str = Query(default='', max_length=500),
    origin: str = Query(default='ALL', pattern='^(ALL|POST|ARTIFACT)$'),
    state: str = Query(default='ALL', pattern='^(ALL|APPROVED|PLANNED|PUBLISHED|ATTENTION)$'),
    kind: str = Query(default='', max_length=200),
    series: str = Query(default='', max_length=200), category: str = Query(default='', max_length=200),
    platform: str = Query(default='', pattern='^(|NONE|telegram|instagram|x|youtube|facebook|tiktok)$'), limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0), session: AsyncSession = Depends(get_session)):
    meta = ArtifactModel.artifact_metadata
    text = func.coalesce(ArtifactModel.content, meta['caption'].astext, '')
    title = func.coalesce(func.nullif(ArtifactOrganizationModel.title, ''), func.nullif(meta['title'].astext, ''), func.nullif(meta['original_filename'].astext, ''), func.nullif(func.substr(text, 1, 120), ''), cast(ArtifactModel.id, String))
    artifacts = select(ArtifactModel.id.label('id'), literal('ARTIFACT').label('origin'),
        ArtifactModel.kind.label('kind'), title.label('title'), text.label('content'),
        ArtifactModel.created_at.label('created_at'), _state(ArtifactModel.id, 'ARTIFACT').label('state'),
        func.coalesce(ArtifactOrganizationModel.series, '').label('series'),
        func.coalesce(ArtifactOrganizationModel.category, '').label('category')
        ).outerjoin(ArtifactOrganizationModel, ArtifactOrganizationModel.artifact_id == ArtifactModel.id).where(
        ArtifactModel.review_status == 'APPROVED', ArtifactModel.status == 'AVAILABLE', ArtifactModel.kind != 'POST',
        func.coalesce(meta['source_type'].astext, '') != 'PLATFORM_VARIANT')
    posts = select(PostModel.id.label('id'), literal('POST').label('origin'),
        func.coalesce(KnowledgeUnitModel.kind, 'TEXT').label('kind'), KnowledgeUnitModel.title.label('title'),
        PostModel.content.label('content'), PostModel.created_at.label('created_at'), _state(PostModel.id, 'POST').label('state'),
        literal('').label('series'), literal('').label('category')
        ).join(KnowledgeUnitModel, KnowledgeUnitModel.id == PostModel.knowledge_unit_id).where(PostModel.status == 'APPROVED')
    combined = union_all(posts, artifacts).subquery()
    conditions = []
    if origin != 'ALL': conditions.append(combined.c.origin == origin)
    if state != 'ALL': conditions.append(combined.c.state == state)
    if kind: conditions.append(combined.c.kind == kind)
    if series: conditions.append(combined.c.series == series)
    if category: conditions.append(combined.c.category == category)
    if platform:
        selected = exists(select(DistributionSelectionModel.artifact_id).where(
            DistributionSelectionModel.artifact_id == combined.c.id,
            func.jsonb_array_length(DistributionSelectionModel.platforms) > 0
            if platform == 'NONE' else DistributionSelectionModel.platforms.contains([platform])))
        # Editorial legacy posts have no central destination selection; they are
        # never inferred as selected or unselected by these artifact-only filters.
        conditions.extend([combined.c.origin == 'ARTIFACT', ~selected if platform == 'NONE' else selected])
    if q.strip():
        needle = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        conditions.append(or_(combined.c.title.ilike(needle, escape='\\'), combined.c.content.ilike(needle, escape='\\'), combined.c.series.ilike(needle, escape='\\'), combined.c.category.ilike(needle, escape='\\'), cast(combined.c.id, String).ilike(needle, escape='\\')))
    total = (await session.execute(select(func.count()).select_from(combined).where(*conditions))).scalar_one()
    rows = (await session.execute(select(combined).where(*conditions).order_by(combined.c.created_at.desc(), combined.c.origin, combined.c.id).limit(limit).offset(offset))).mappings().all()
    ids = [row['id'] for row in rows]
    artifacts_by_id = {a.id:a for a in (await session.execute(select(ArtifactModel).where(ArtifactModel.id.in_(ids)))).scalars()} if ids else {}
    selections = {s.artifact_id:s for s in (await session.execute(select(DistributionSelectionModel).where(DistributionSelectionModel.artifact_id.in_(ids)))).scalars()} if ids else {}
    copies = {}
    if ids:
        for copy in (await session.execute(select(PlatformCopyModel).where(PlatformCopyModel.artifact_id.in_(ids)))).scalars():
            copies.setdefault(copy.artifact_id, []).append(copy)
    plans = {}
    if ids:
        relevant = ScheduleModel.status.in_(['DRAFT', 'ACTIVE', 'PAUSED']) & ScheduleItemModel.status.in_(['PENDING', 'PROCESSING'])
        needs_attention = (ScheduleModel.status != 'CANCELLED') & _failed_item()
        plan_rows = (await session.execute(select(ScheduleItemModel.post_id, ScheduleItemModel.artifact_id,
            ScheduleModel.id, ScheduleModel.status, needs_attention.label('needs_attention'), relevant.label('relevant'))
            .join(ScheduleModel, ScheduleModel.id == ScheduleItemModel.schedule_id)
            .where(or_(ScheduleItemModel.post_id.in_(ids), ScheduleItemModel.artifact_id.in_(ids)))
            .order_by(case((needs_attention, 0), (relevant, 1), else_=2),
                      ScheduleModel.created_at.desc(), ScheduleModel.id))).all()
        for post_id, artifact_id, plan_id, plan_status, attention, active in plan_rows:
            plans.setdefault(('POST' if post_id else 'ARTIFACT', post_id or artifact_id),
                (str(plan_id), plan_status, 'ATTENTION' if attention else 'CURRENT' if active else 'HISTORY'))
    from app.application.central_platform_copies import evaluate
    from app.application.distribution_readiness import source_fingerprint
    items=[]
    for row in rows:
        data=dict(row); data['id']=str(row['id']); data['content_preview']=data.pop('content')[:300]
        artifact = artifacts_by_id.get(row['id']) if row['origin']=='ARTIFACT' else None
        selection = selections.get(row['id']) if artifact else None
        prepared=copies.get(row['id'],[]) if artifact else []
        plan = plans.get((row['origin'],row['id']))
        data.update(latest_plan_id=plan[0] if plan else None, latest_plan_status=plan[1] if plan else None, plan_link_reason=plan[2] if plan else None, selected_platforms=selection.platforms if selection else [],
            selection_stale=bool(selection and selection.source_fingerprint != source_fingerprint(artifact)),
            prepared_copies=len(prepared), fields_validated=sum(evaluate(artifact,c)['field_status']=='FIELDS_VALIDATED' for c in prepared),
            execution_ready=False,
            preparation_scope='CENTRAL_COPIES' if artifact else 'LEGACY_TELEGRAM')
        items.append(data)
    return {'items':items,'total':total,'limit':limit,'offset':offset,
        'caveat':'مرشح الوجهة يعرض الاختيار المحفوظ للمخرجات فقط، ولو تغير الأصل؛ لا يعني أهلية المنصة أو اتصالها أو إذن تنفيذها. الاعتماد ليس إذناً بالتنفيذ. الفشل يبقى ظاهراً ما لم يثبت تجاوزه لنفس الوجهة والحساب؛ نجاح وجهة لا يغطي فشل أخرى. حالة النشر مبنية على سجل مؤكد بمعرّف خارجي؛ روابط التفاصيل تعرض الوجهات والنتائج. الحقول المقبولة مبدئياً ليست تحققاً من الوسائط أو صلاحيات الحساب.'}
