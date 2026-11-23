"""Dedicated approved photo plus motion pair, never a VIDEO alias."""
from app.application.telegram_albums import child_preview, child_fingerprint
from app.application.manual_artifacts import create_manual_artifact
from app.infrastructure.database.models import ArtifactModel
from sqlalchemy import select
from uuid import UUID


def pair_ids(metadata):
    value = metadata.get('telegram_live_photo')
    if not isinstance(value, dict) or set(value) != {'photo_id', 'video_id'}:
        raise ValueError('Live Photo requires exactly a photo and a motion video.')
    try:
        ids = [UUID(value[key]) for key in ('photo_id', 'video_id')]
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid Live Photo child IDs.') from exc
    if len(set(ids)) != 2:
        raise ValueError('Live Photo requires distinct children.')
    return ids


async def resolve_live_photo(session, metadata, *, check_snapshot=True):
    ids = pair_ids(metadata)
    rows = (await session.execute(select(ArtifactModel).where(ArtifactModel.id.in_(ids)))).scalars().all()
    found = {row.id: row for row in rows}
    children = [found.get(uid) for uid in ids]
    if any(row is None or row.status != 'AVAILABLE' or row.review_status != 'APPROVED' or not row.storage_uri for row in children):
        raise ValueError('Live Photo children must remain approved available media.')
    if children[0].kind != 'IMAGE' or children[0].mime_type not in {'image/jpeg', 'image/png', 'image/webp'} or children[1].kind != 'VIDEO' or children[1].mime_type != 'video/mp4':
        raise ValueError('Live Photo needs one static image and one MP4 motion video, in that order.')
    fingerprints = [child_fingerprint(row) for row in children]
    if check_snapshot and (metadata.get('live_photo_fingerprints') != fingerprints or metadata.get('live_photo_preview') != child_preview(children)):
        raise ValueError('Live Photo children or preview changed; create and review a new pair.')
    return children, fingerprints


async def create_live_photo(session, *, photo_id, video_id, title, storage=None):
    metadata = {'telegram_live_photo': {'photo_id': photo_id, 'video_id': video_id}}
    children, fingerprints = await resolve_live_photo(session, metadata, check_snapshot=False)
    from app.infrastructure.artifact_storage import S3ArtifactStorage, ArtifactStorageError
    from app.domain.telegram_live_photo import validate_live_motion
    storage = storage or S3ArtifactStorage.from_environment()
    try:
        motion = await storage.get_bytes(children[1].storage_uri, max_bytes=10 * 1024 * 1024)
    except ArtifactStorageError as exc:
        raise ValueError('Could not validate the motion file in private storage.') from exc
    validate_live_motion(motion)
    metadata.update(live_photo_fingerprints=fingerprints, live_photo_preview=child_preview(children))
    # Pair fingerprints feed the same transaction-scoped idempotency boundary.
    import hashlib, json
    from sqlalchemy import text
    key = int.from_bytes(hashlib.sha256(json.dumps(metadata['telegram_live_photo'], sort_keys=True).encode()).digest()[:8], 'big', signed=True)
    await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
    existing = (await session.execute(select(ArtifactModel).where(ArtifactModel.kind == 'TEXT', ArtifactModel.review_status.in_(['DRAFT', 'APPROVED']), ArtifactModel.artifact_metadata['live_photo_fingerprints'] == fingerprints))).scalars().all()
    for row in existing:
        if row.artifact_metadata.get('telegram_live_photo') == metadata['telegram_live_photo']:
            from app.application.artifacts import load_artifact
            return await load_artifact(session, row.id)
    content = str((children[1].artifact_metadata or {}).get('caption') or title)
    from app.adapters.publishing.telegram import telegram_html_content
    telegram_html_content(content, max_visible_characters=1024)
    return await create_manual_artifact(session, kind='TEXT', title=title, content=content, live_photo_metadata=metadata)
