"""Read-only library paging, global filters and compact result identity index."""
from sqlalchemy import select, func, cast, String, case, literal
from app.infrastructure.database.models import ArtifactModel as A, ArtifactOrganizationModel as O
from app.application.generic_artifact_review import _payload
from app.application.content_organization import for_ids


def expressions():
    m = A.artifact_metadata
    def string(value):
        # JSON numbers/objects are not strings in the existing browser helpers.
        return case((func.jsonb_typeof(value) == 'string', value.astext), else_=None)
    def trim(value):
        return func.btrim(value, ' \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff')
    raw_filename = string(m['original_filename'])
    filename = func.regexp_replace(func.coalesce(raw_filename, ''), r'^\d+-', '')
    series = func.coalesce(func.nullif(O.series, ''), case(
        (filename.op('~')(r'^b\d+v\d+'), 'وش معنى'),
        (filename.op('~')(r'^womdha-\d+'), 'ومضة'),
        (filename.op('~')(r'^v\d+-'), 'فيديو تعريفي'),
        else_=func.coalesce(string(m['series']), 'غير مصنف')))
    category = func.coalesce(func.nullif(O.category, ''), 'غير مصنف')
    source = func.coalesce(string(m['source_type']), 'GENERATED')
    caption = trim(func.coalesce(string(m['caption']), ''))
    first_line = trim(func.split_part(caption, '\n', 1))
    title = func.coalesce(func.nullif(O.title, ''), func.nullif(trim(string(m['title'])), ''),
        case((func.length(caption) > 0, case((func.length(first_line) > 90, func.substr(first_line, 1, 90) + '…'), else_=first_line))),
        case((func.length(trim(raw_filename)) > 0, filename)), literal('مخرج ') + A.kind)
    search = func.lower(func.concat_ws(' ', cast(A.id, String), O.title, O.category, O.series, A.content,
        string(m['title']), string(m['caption']), string(m['full_caption']), string(m['description']),
        raw_filename, series, string(m['video_library']['source_original']),
        string(m['video_library']['tiktok_text']), string(m['video_library']['telegram_caption'])))
    return series, category, source, title, search


async def library_page(session, review_status='DRAFT', q='', kind='ALL', source='ALL', series='ALL', category='ALL', sort='newest', limit=12, offset=0, include_items=True):
    if review_status not in {'DRAFT','APPROVED','REJECTED'} or sort not in {'newest','oldest','title','kind'}:
        raise ValueError('Unsupported library state or sort.')
    se, ca, so, ti, text = expressions()
    base = [A.kind != 'POST', A.review_status == review_status]
    conditions = list(base)
    for value, expression in [(kind,A.kind),(source,so),(series,se),(category,ca)]:
        if value != 'ALL': conditions.append(expression == value)
    if q.strip(): conditions.append(text.contains(q.strip().lower(), autoescape=True))
    # Explicit ID tie-breakers keep page boundaries stable for equal values.
    order = {'newest':[A.created_at.desc(), A.id.desc()], 'oldest':[A.created_at.asc(), A.id.asc()],
        'title':[ti.asc(),A.id.asc()], 'kind':[A.kind.collate('C').asc(),A.created_at.desc(),A.id.desc()]}[sort]
    joined = lambda stmt: stmt.select_from(A).outerjoin(O,O.artifact_id==A.id)
    rows = (await session.execute(joined(select(A)).where(*conditions).order_by(*order).offset(offset).limit(limit))).scalars().all() if include_items else []
    labels = await for_ids(session,[r.id for r in rows])
    # The identity index carries no original text, captions, storage URI or media.
    index_rows = (await session.execute(joined(select(A.id,A.kind,A.status,A.review_status,A.created_at,ti.label('title'),so.label('source_type'),
        A.artifact_metadata['telegram_album'].astext.is_not(None).label('album'),A.artifact_metadata['telegram_live_photo'].astext.is_not(None).label('live_photo')))
        .where(*conditions).order_by(*order))).mappings().all()
    index=[]
    for r in index_rows:
        index.append(dict(id=str(r['id']),kind=r['kind'],status=r['status'],review_status=r['review_status'],
            created_at=r['created_at'],
            metadata=dict(title=r['title'],source_type=r['source_type'],telegram_album=True if r['album'] else None,telegram_live_photo=True if r['live_photo'] else None)))
    options=(await session.execute(joined(select(se.label('series'),ca.label('category'))).where(*base).distinct())).mappings().all()
    return dict(items=[{**_payload(r),'organization':labels.get(str(r.id))} for r in rows],index=index,total=len(index),limit=limit,offset=offset,
        filter_options=dict(series=sorted({r['series'] for r in options}),categories=sorted({r['category'] for r in options})))
