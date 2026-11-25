from types import SimpleNamespace as N
from datetime import datetime,timezone
from uuid import uuid4
from app.api.routes import _schedule_payload


def test_saved_plan_summary_does_not_rename_or_invent_destination():
    now=datetime.now(timezone.utc)
    artifact=N(artifact_metadata={'title':'عنوان أصلي محفوظ'},kind='VIDEO',content=None,source_knowledge_unit_id=uuid4())
    item=N(id=uuid4(),position=1,artifact_id=uuid4(),artifact=artifact,publication=None,status='PUBLISHED',scheduled_at=now,attempts=1,publication_id=None,published_at=now,last_error=None)
    plan=N(id=uuid4(),name='جدولة مسودة abc',status='COMPLETED',timezone='Asia/Riyadh',items=[item],telegram_review=None,created_at=now,updated_at=now,started_at=now,completed_at=now)
    result=_schedule_payload(plan)
    assert result['name']==plan.name
    assert result['content_summary']==[{'title':'عنوان أصلي محفوظ','kind':'VIDEO'}]
    assert result['platform']=='telegram'
    assert result['destination_label'] is None
    plan.telegram_review={'channel_label':'قناة مختارة','destination':'@expected'}
    assert _schedule_payload(plan)['destination_label']=='قناة مختارة'

async def test_progress_has_separate_counts_and_is_read_only():
    from app.api.workspace_progress import progress
    class Session:
        def __init__(self):self.calls=[];self.results=iter([[('DRAFT',2),('APPROVED',3)], [('DRAFT',4),('APPROVED',5)]]);self.scalars=iter([6,10,7,8,9])
        async def execute(self,query):
            self.calls.append(str(query));return N(all=lambda:next(self.results))
        async def scalar(self,query):self.calls.append(str(query));return next(self.scalars)
    session=Session();result=await progress(session)
    assert result['materials']=={'DRAFT':2,'APPROVED':3}
    assert result['editorial_posts']=={'DRAFT':4,'APPROVED':5}
    assert result['platform_copies']==10 and result['legacy_platform_variants']==6 and result['pdf_sources']==9
    assert result['schedule_items']=={'failed':7,'pending_or_processing':8}
    assert all(q.lstrip().startswith('SELECT') for q in session.calls)
    assert 'PLATFORM_VARIANT' in str(__import__('inspect').getsource(progress))
