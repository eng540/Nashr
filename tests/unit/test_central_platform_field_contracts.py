from types import SimpleNamespace
from app.application.central_platform_copies import evaluate
from app.application.distribution_readiness import source_fingerprint


def evaluate_fields(platform,**fields):
    row=SimpleNamespace(kind='VIDEO',content='أصل',artifact_metadata={},review_status='APPROVED',status='AVAILABLE',storage_uri='s3://file',mime_type='video/mp4')
    copy=SimpleNamespace(platform=platform,fields={'title':'عنوان','description':'وصف','tags':[],'alt_text':'',**fields},source_fingerprint=source_fingerprint(row),origin='USER_EDITED',version=1,updated_at=None)
    return evaluate(row,copy)


def test_youtube_description_is_bytes_not_characters():
    assert evaluate_fields('youtube',description='ع'*2500)['field_status']=='FIELDS_VALIDATED'
    assert evaluate_fields('youtube',description='ع'*2501)['field_status']=='BLOCKED'
    assert evaluate_fields('youtube',title='ط'*101)['field_status']=='BLOCKED'
    assert evaluate_fields('youtube',tags=['foo bar']*56)['field_status']=='BLOCKED'


def test_instagram_mentions_hashtags_and_pending_media_checks():
    result=evaluate_fields('instagram',description=' '.join('#tag'+str(i) for i in range(31)))
    assert result['field_status']=='BLOCKED'
    result=evaluate_fields('instagram')
    assert result['field_status']=='FIELDS_VALIDATED' and result['media_checks_pending']
    assert result['execution_status']=='NOT_AUTHORIZED'
    assert evaluate_fields('x')['field_status']=='BLOCKED'
