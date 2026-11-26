from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from app.application.instagram_unified_execution import describe


def job(state='DRAFT'):
    return NS(id=uuid4(),artifact_id=uuid4(),state=state,kind='VIDEO',account_id='100',
        connection_binding={'login_mode':'UNIFIED','username':'synthetic'},caption='النص الكامل',alt_text='',
        share_to_feed=True,media_sha256='a'*64,copy_version=1,created_at=datetime.now(timezone.utc),
        container_id=None,media_id=None,permalink=None,error_code=None)


def test_unapproved_draft_never_infers_authority():
    r=describe(job());assert r['can_propose'] and not r['approval_recorded'] and not r['execution_enabled']
    assert r['remaining_gates'] and r['dispatch_state'] is None


@pytest.mark.parametrize('state,dispatch,decision,expired,active',[
    ('DRAFT','PENDING','APPROVED',False,True),
    ('DRAFT','PENDING','APPROVED',True,False),
    ('DRAFT','CANCELLED','REVOKED',False,False),
    ('DRAFT','PENDING','REVOKED',False,False),
    ('PUBLISHED','PUBLISHED','APPROVED',True,False),
    ('PUBLISHED_ID_KNOWN','RESULT_KNOWN','APPROVED',True,False),
    ('PUBLISH_UNKNOWN','RECONCILE_ONLY','APPROVED',False,False),
    ('DRAFT','BLOCKED','APPROVED',False,False),
    ('PUBLISHED','PUBLISHED','REVOKED',False,False),
])
def test_projection_reports_recorded_decision_without_enabling_replay(state,dispatch,decision,expired,active):
    now=datetime.now(timezone.utc)
    d=NS(state=dispatch,due_at=now)
    approval=NS(state=decision,expires_at=now+timedelta(minutes=-1 if expired else 10))
    r=describe(job(state),d,approval)
    assert r['dispatch_state']==dispatch and r['decision_state']==decision
    assert r['approval_recorded']==(decision=='APPROVED')
    assert r['approval_expired']==(decision=='APPROVED' and expired)
    assert r['execution_enabled']==active
    assert not r['can_propose'] and not r['remaining_gates']
    assert not r['media_exposure_enabled']
