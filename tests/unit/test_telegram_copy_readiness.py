from types import SimpleNamespace
from app.application.telegram_copy_readiness import telegram_copy_blockers


def row(kind='TEXT',content='نص صالح',metadata=None,mime_type='text/plain',storage_uri=None):
    return SimpleNamespace(kind=kind,content=content,artifact_metadata=metadata or {},mime_type=mime_type,storage_uri=storage_uri)


def test_publisher_text_format_and_limit_are_checked_without_trimming():
    assert telegram_copy_blockers(row()) == []
    assert telegram_copy_blockers(row(content='<b>غير مغلق'))
    assert telegram_copy_blockers(row(content='ن'*4097))
    assert telegram_copy_blockers(row(content='<b>'+'ن'*4096+'</b>')) == []


def test_media_caption_limit_and_mime_are_not_reported_eligible():
    good=row(kind='VIDEO',content=None,metadata={'caption':'تعليق'},mime_type='video/mp4',storage_uri='s3://test/video.mp4')
    assert telegram_copy_blockers(good) == []
    good.artifact_metadata={'caption':'ن'*1025}
    assert telegram_copy_blockers(good)
    good.artifact_metadata={'caption':'قصير'};good.mime_type='image/jpeg'
    assert telegram_copy_blockers(good)


def test_native_payload_and_structured_quiz_are_checked():
    assert telegram_copy_blockers(row(metadata={'telegram_native':{'type':'LOCATION','latitude':0,'longitude':0}})) == []
    assert telegram_copy_blockers(row(metadata={'telegram_native':{'type':'LOCATION','latitude':999,'longitude':0}}))
    assert telegram_copy_blockers(row(kind='QUIZ',metadata={'quiz':{}}))
