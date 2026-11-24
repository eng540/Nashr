"""Catalog-only labels. Never change content, review, platform copy or execution."""
from datetime import datetime,timezone
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel,ArtifactOrganizationModel as Organization


def payload(row):
    return {'title':row.title,'series':row.series,'category':row.category,'version':row.version,'updated_at':row.updated_at.isoformat()}

async def for_ids(session,ids):
    if not ids:return {}
    rows=(await session.execute(select(Organization).where(Organization.artifact_id.in_(ids)))).scalars().all()
    return {str(row.artifact_id):payload(row) for row in rows}

async def save(session,ids,fields,versions):
    if len(ids)!=len(set(ids)):raise ValueError('تحديد مكرر. اختر كل مادة مرة واحدة.')
    if not fields or set(fields)-{'title','series','category'}:raise ValueError('اختر حقلاً تنظيمياً واحداً على الأقل.')
    if 'title' in fields and len(ids)!=1:raise ValueError('العنوان لمادة واحدة فقط؛ لا نستبدل عناوين دفعة بنص واحد.')
    if any(version<0 for version in versions.values()) or set(versions)!=set(str(uid) for uid in ids):raise ValueError('إصدارات التنظيم غير مكتملة. أعد تحميل المواد.')
    rows=(await session.execute(select(ArtifactModel).where(ArtifactModel.id.in_(ids)).order_by(ArtifactModel.id).with_for_update())).scalars().all()
    if len(rows)!=len(ids) or any(row.kind=='POST' or (row.artifact_metadata or {}).get('source_type')=='PLATFORM_VARIANT' for row in rows):raise ValueError('اختر مواد أصلية موجودة، لا نسخ منصات أو منشورات المسار القديم.')
    existing=(await session.execute(select(Organization).where(Organization.artifact_id.in_(ids)))).scalars().all();by_id={row.artifact_id:row for row in existing}
    for row in rows:
        current=by_id.get(row.id)
        if versions[str(row.id)]!=(current.version if current else 0):raise ValueError('تغير تنظيم إحدى المواد في نافذة أخرى. لم نحفظ جزءاً من الدفعة؛ أعد التحميل.')
    for row in rows:
        current=by_id.get(row.id)
        if current is None:current=Organization(artifact_id=row.id,title='',series='',category='',version=0);session.add(current)
        for key,value in fields.items():setattr(current,key,value.strip())
        current.version+=1;current.updated_at=datetime.now(timezone.utc)
    await session.commit()
    return {'updated':len(rows),'organization':await for_ids(session,ids),'content_changed':False,'approval_changed':False,'schedules_changed':False,'sent_messages':0}
