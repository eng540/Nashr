from types import SimpleNamespace
from app.domain.telegram_copy import telegram_publish_text
from app.application.telegram_copy_readiness import telegram_copy_blockers


def test_original_content_wins_without_trimming_and_metadata_is_fallback():
    row=SimpleNamespace(kind='VIDEO',content='  نص أصلي كامل  ',artifact_metadata={'caption':'وصف قديم'})
    assert telegram_publish_text(row)=='  نص أصلي كامل  '
    row.content=None
    assert telegram_publish_text(row)=='وصف قديم'
    row.content=''
    assert telegram_publish_text(row)==''


def test_no_caption_kinds_do_not_preview_or_validate_unpublished_caption():
    for kind,mime in [('VIDEO_NOTE','video/mp4'),('STICKER','image/webp')]:
        row=SimpleNamespace(kind=kind,content='ن'*5000,artifact_metadata={'caption':'وصف طويل'},storage_uri='s3://test/file',mime_type=mime)
        assert telegram_publish_text(row)==''
        assert telegram_copy_blockers(row)==[]
