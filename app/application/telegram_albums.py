"""Resolve approved album children and bind their content to album approval."""
import hashlib
import json
from sqlalchemy import select, text
from app.domain.telegram_albums import album_ids, validate_album_group
from app.infrastructure.database.models import ArtifactModel


def child_fingerprint(row):
    value = {'id': str(row.id), 'kind': row.kind, 'storage_uri': row.storage_uri,
             'mime_type': row.mime_type, 'metadata': row.artifact_metadata or {}}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def child_preview(children):
    return [{'id': str(row.id), 'kind': row.kind,
        'filename': (row.artifact_metadata or {}).get('original_filename'),
        'caption': (row.artifact_metadata or {}).get('caption', '')} for row in children]


async def resolve_album(session, metadata, *, check_snapshot=True):
    ids = album_ids(metadata['telegram_album'])
    rows = (await session.execute(select(ArtifactModel).where(ArtifactModel.id.in_(ids)))).scalars().all()
    found = {row.id: row for row in rows}
    children = []
    for uid in ids:
        row = found.get(uid)
        if row is None or row.status != 'AVAILABLE' or row.review_status != 'APPROVED' or not row.storage_uri:
            raise ValueError('All album children must remain approved and available stored media.')
        children.append(row)
    validate_album_group([row.kind for row in children])
    allowed = {'IMAGE': {'image/png','image/jpeg','image/webp'}, 'VIDEO': {'video/mp4'}, 'AUDIO': {'audio/mpeg','audio/mp4'}, 'DOCUMENT': {'application/octet-stream'}}
    if any(row.mime_type not in allowed[row.kind] for row in children):
        raise ValueError('Album child MIME does not match its approved kind.')
    current = [child_fingerprint(row) for row in children]
    if check_snapshot and metadata.get('album_child_fingerprints') != current:
        raise ValueError('Album children changed after selection; create and review a new album.')
    if check_snapshot and metadata.get("album_preview") != child_preview(children):
        raise ValueError("Album preview does not match its approved children.")
    return children, current


async def create_album(session, *, artifact_ids, title):
    from app.application.manual_artifacts import create_manual_artifact
    metadata = {'telegram_album': {'artifact_ids': artifact_ids}}
    children, fingerprints = await resolve_album(session, metadata, check_snapshot=False)
    metadata['album_child_fingerprints'] = fingerprints
    metadata['album_preview'] = child_preview(children)
    content = title + '\n' + '\n'.join(f"{i+1}. {item['kind']}: {item['filename']}\n{item['caption']}" for i, item in enumerate(metadata['album_preview']))
    # Repeated UI clicks reuse the same unchanged selection instead of creating
    # independent wrappers that could later be sent twice.
    lock_key = int.from_bytes(hashlib.sha256(json.dumps(metadata['telegram_album'], sort_keys=True).encode()).digest()[:8], 'big', signed=True)
    await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
    candidates = (await session.execute(select(ArtifactModel).where(
        ArtifactModel.kind == 'TEXT', ArtifactModel.review_status.in_(['DRAFT', 'APPROVED']),
        ArtifactModel.artifact_metadata['album_child_fingerprints'] == fingerprints))).scalars().all()
    for candidate in candidates:
        if (candidate.artifact_metadata or {}).get('telegram_album') == metadata['telegram_album']:
            from app.application.artifacts import load_artifact
            return await load_artifact(session, candidate.id)
    return await create_manual_artifact(session, kind='TEXT', title=title, content=content, album_metadata=metadata)
