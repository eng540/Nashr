"""Pure grouping rules for approved Telegram media albums."""
from uuid import UUID

ALBUM_KINDS = frozenset({'IMAGE', 'VIDEO', 'AUDIO', 'DOCUMENT'})


def album_ids(value):
    if not isinstance(value, dict) or set(value) != {'artifact_ids'}:
        raise ValueError('Album requires only artifact_ids.')
    items = value['artifact_ids']
    if not isinstance(items, list) or not 2 <= len(items) <= 10:
        raise ValueError('Album requires2to10media items.')
    try:
        ids = [UUID(item) for item in items if isinstance(item, str)]
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Album requires valid artifact IDs.') from exc
    if len(ids) != len(items) or len(set(ids)) != len(ids):
        raise ValueError('Album artifact IDs must be valid and unique.')
    return ids


def validate_album_group(kinds):
    if not 2 <= len(kinds) <= 10 or not set(kinds) <= ALBUM_KINDS:
        raise ValueError('Unsupported album media types or count.')
    values = set(kinds)
    if values <= {'IMAGE', 'VIDEO'} or values in ({'AUDIO'}, {'DOCUMENT'}):
        return
    raise ValueError('Audio and documents must each form a same-type album.')
