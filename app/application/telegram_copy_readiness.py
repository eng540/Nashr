from app.domain.telegram_copy import telegram_publish_text
"""Reuse the publisher's static payload checks without network or media reads."""
from app.adapters.publishing.telegram import telegram_html_content
from app.domain.telegram_payloads import native_payload
from app.domain.quizzes import QuizPayload
from app.domain.telegram_albums import album_ids
from app.application.telegram_live_photos import pair_ids
from app.domain.telegram_media import MEDIA_METHODS, NO_CAPTION


def telegram_copy_blockers(row):
    meta = row.artifact_metadata or {}
    text = telegram_publish_text(row)
    try:
        if meta.get('telegram_native') is not None:
            if row.kind != 'TEXT':
                raise ValueError('نوع الحاوية يجب أن يكون نصاً.')
            native_payload(meta['telegram_native'])
        elif meta.get('telegram_album') is not None:
            album_ids(meta['telegram_album'])
            for item in meta.get('album_preview') or []:
                if item.get('caption'):
                    telegram_html_content(item['caption'], max_visible_characters=1024)
        elif meta.get('telegram_live_photo') is not None:
            pair_ids(meta)
            telegram_html_content(text, max_visible_characters=1024)
        elif row.kind == 'QUIZ':
            QuizPayload.from_dict(meta.get('quiz') or {})
        elif row.kind == 'TEXT':
            telegram_html_content(text)
        elif row.kind in MEDIA_METHODS:
            if not row.storage_uri:
                raise ValueError('ملف الوسيط الأصلي غير متاح.')
            allowed = {
                'IMAGE': {'image/png', 'image/jpeg', 'image/webp'}, 'VIDEO': {'video/mp4'},
                'AUDIO': {'audio/mpeg', 'audio/mp4'}, 'ANIMATION': {'image/gif', 'video/mp4'},
                'VOICE': {'audio/ogg', 'audio/mpeg', 'audio/mp4'}, 'VIDEO_NOTE': {'video/mp4'},
                'STICKER': {'image/webp', 'video/webm', 'application/x-tgsticker'},
            }
            if row.kind != 'DOCUMENT' and row.mime_type not in allowed.get(row.kind, set()):
                raise ValueError('صيغة الوسيط لا تطابق نوع Telegram.')
            if row.kind not in NO_CAPTION:
                telegram_html_content(text, max_visible_characters=1024)
        else:
            raise ValueError('نوع المادة غير مدعوم في مسار Telegram.')
    except (ValueError, TypeError, KeyError) as exc:
        return ['تحقق من حمولة Telegram قبل المتابعة: ' + str(exc)]
    return []
