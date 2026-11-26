"""Offline coverage check of a deliberately reduced recovery inventory.

Never connects to a database/provider or reads secret values. Input must contain
only source payload lengths, artifact IDs/storage references/metadata and media
references, not full DB rows. Reports hashed reference IDs, not paths or URLs.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


def reference_id(value):
    return hashlib.sha256(value.encode()).hexdigest()


def stored_references(value):
    if isinstance(value, str):
        if value.startswith('s3://'):
            yield value
    elif isinstance(value, list):
        for item in value:
            yield from stored_references(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {'storage_uri', 'storage_path'} and isinstance(item, str) and item:
                yield item
            else:
                yield from stored_references(item)


def object_path(uri, root):
    p = urlsplit(uri)
    if p.scheme != 's3' or not p.netloc or p.query or p.fragment or p.username or p.password:
        raise ValueError('Invalid object reference.')
    parts = p.path.lstrip('/').split('/')
    if any(x in {'', '.', '..'} for x in parts) or '\\' in uri or '%' in uri:
        raise ValueError('Unsafe object key.')
    path = root.resolve() / p.netloc
    for part in parts:
        path /= part
    return safe_file(path, root)


def safe_file(path, root):
    root = root.resolve()
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    # Reject symlink parents as well as a linked leaf; no file opens outside root.
    try:
        relative = path.absolute().relative_to(root)
    except ValueError:
        return None
    current = root
    for part in relative.parts:
        if part in {'..', '.'}:
            return None
        current /= part
        if current.is_symlink():
            return None
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        return None
    return resolved if resolved.is_file() else None


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def coverage(data, source_root, object_root):
    if source_root.is_symlink() or object_root.is_symlink():
        raise ValueError('Inventory roots cannot be symlinks.')
    source_root, object_root = source_root.resolve(), object_root.resolve()
    source_counts = {'payload_present': 0, 'local_only_present': 0, 'object_reference': 0, 'missing_payload_and_file': 0}
    source_checks = []
    for source in data.get('sources', []):
        count = source.get('payload_bytes', 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError('Payload lengths must be nonnegative integers.')
        if count > 0:
            state = 'payload_present'
        elif str(source.get('storage_path', '')).startswith('s3://'):
            state = 'object_reference'
        elif safe_file(source.get('storage_path', ''), source_root):
            state = 'local_only_present'
        else:
            state = 'missing_payload_and_file'
        source_counts[state] += 1
        source_checks.append({'record_id': reference_id(str(source.get('id', ''))), 'state': state})
    refs = {s['storage_path'] for s in data.get('sources', [])
            if str(s.get('storage_path', '')).startswith('s3://')}
    artifact_ids = {str(row['id']) for row in data.get('artifacts', [])}
    missing_children = set()
    hashes = {}
    def children(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'photo_id', 'video_id'} and isinstance(child, str):
                    if child not in artifact_ids:
                        missing_children.add(reference_id(child))
                elif key == 'artifact_ids' and isinstance(child, list):
                    for aid in child:
                        if str(aid) not in artifact_ids:
                            missing_children.add(reference_id(str(aid)))
                else:
                    children(child)
        elif isinstance(value, list):
            for child in value:
                children(child)
    for name in ['artifacts', 'platform_copy_media']:
        for row in data.get(name, []):
            refs.update(stored_references(row))
            children(row.get('metadata', {}))
            uri, expected = row.get('storage_uri'), row.get('sha256')
            if uri and expected:
                hashes.setdefault(uri, set()).add(expected)
    objects = []
    for uri in sorted(refs):
        rid = reference_id(uri)
        try:
            if uri.startswith('s3://'):
                path = object_path(uri, object_root)
            elif urlsplit(uri).scheme:
                raise ValueError('Unsupported remote reference.')
            else:
                path = safe_file(uri, source_root)
        except ValueError:
            state = 'invalid_reference'
        else:
            if not path:
                state = 'missing_object'
            elif path.stat().st_size == 0:
                state = 'empty_object'
            elif uri in hashes and (len(hashes[uri]) != 1 or file_hash(path) not in hashes[uri]):
                state = 'hash_mismatch'
            elif uri in hashes:
                state = 'present_hash_verified'
            else:
                state = 'present_hash_unavailable'
        objects.append({'reference_id': rid, 'state': state})
    missing = source_counts['missing_payload_and_file'] + len(missing_children) + sum(o['state'] in {'missing_object', 'empty_object', 'invalid_reference', 'hash_mismatch'} for o in objects)
    # Completeness cannot be certified merely because a caller supplied no rows.
    return {'scope': 'OFFLINE_INPUT_ONLY', 'source_counts': source_counts, 'source_checks': source_checks,
            'object_count': len(objects), 'objects': objects, 'missing_child_record_ids': sorted(missing_children),
            'blocking_gaps': missing, 'input_has_rows': bool(source_checks or artifact_ids or data.get('platform_copy_media')),
            'live_inventory_verified': False, 'durable_backup_created': False,
            'provider_access_checked': False, 'source_payload_bytes_hashed': False,
            'notes': ['Payload presence is not payload integrity.', 'Objects without a trusted expected hash are not hash-verified.',
                      'Remote HTTP references and expiring provider capabilities are not recovered.',
                      'Caller must independently establish inventory export completeness.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--object-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = coverage(json.loads(args.inventory.read_text()), args.source_root, args.object_root)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['scope', 'source_counts', 'object_count', 'blocking_gaps', 'input_has_rows', 'live_inventory_verified', 'durable_backup_created']}))
    raise SystemExit(2 if report['blocking_gaps'] or not report['input_has_rows'] else 0)


if __name__ == '__main__':
    main()
