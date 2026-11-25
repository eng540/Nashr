from types import SimpleNamespace as S
import pytest
from app.application.facebook_copy_fields import blockers
from app.application.central_platform_copies import evaluate
from app.application.distribution_readiness import source_fingerprint

def fields(**kw):return dict(title='',description='النص كامل',tags=[],alt_text='',**kw)

@pytest.mark.parametrize('kind',['TEXT','IMAGE','VIDEO'])
def test_exact_fields_only_and_no_mutation(kind):
    f=fields();assert blockers(kind,f)==[]
    for key,value in [('title','عنوان'),('tags',['وسم']),('alt_text','وصف')]:
        changed={**f,key:value};before=dict(changed)
        assert blockers(kind,changed) and changed==before

def test_type_specific_local_limits_and_empty_photo():
    assert blockers('TEXT',{**fields(),'description':' '})
    assert not blockers('IMAGE',{**fields(),'description':''})
    assert not blockers('VIDEO',{**fields(),'description':'أ'*2200})
    assert blockers('VIDEO',{**fields(),'description':'أ'*2201})
    assert blockers('TEXT',{**fields(),'description':'أ'*60001})
    assert blockers('QUIZ',fields())

@pytest.mark.parametrize('kind',['TEXT','IMAGE','VIDEO'])
def test_bank_fields_truth_never_execution_grant(kind):
    a=S(kind=kind,content='الأصل',storage_uri=None,mime_type='image/jpeg',artifact_metadata={},review_status='APPROVED',status='AVAILABLE')
    c=S(platform='facebook',fields=fields(),source_fingerprint=source_fingerprint(a),selected_media_id=None,origin='USER_EDITED',version=2,updated_at=None)
    d=evaluate(a,c)
    assert d['field_status']=='FIELDS_VALIDATED' and d['execution_status']=='NOT_AUTHORIZED'
    assert d['sources'] and d['media_checks_pending']
    assert 'لم يكتمل ملف' not in str(d['blockers'])
    c.fields={**fields(),'title':'عنوان محفوظ'}
    assert evaluate(a,c)['field_status']=='BLOCKED'
    assert a.content=='الأصل' and c.fields['title']=='عنوان محفوظ'
