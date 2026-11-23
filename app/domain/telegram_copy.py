"""One unmodified text source for Telegram preview, drafts and execution."""
from app.domain.telegram_media import NO_CAPTION


def telegram_publish_text(artifact):
    kind = getattr(artifact.kind, 'value', artifact.kind)
    if kind in NO_CAPTION:
        return ''
    if artifact.content is not None:
        return artifact.content
    metadata = getattr(artifact, 'artifact_metadata', None)
    if metadata is None:
        metadata = getattr(artifact, 'metadata', None)
    return str((metadata or {}).get('caption') or '')
