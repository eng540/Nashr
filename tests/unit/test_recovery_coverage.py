import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('recovery_coverage', Path(__file__).parents[2] / 'scripts/recovery_coverage.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def roots(tmp_path):
    source, objects = tmp_path / 'sources', tmp_path / 'objects'
    source.mkdir()
    objects.mkdir()
    return source, objects


def test_payload_and_missing_local(roots):
    source, objects = roots
    (source / 'legacy.pdf').write_bytes(b'pdf')
    report = module.coverage({'sources': [
        {'id': 'a', 'storage_path': '/old/pdf', 'payload_bytes': 3},
        {'id': 'b', 'storage_path': 'legacy.pdf', 'payload_bytes': 0},
        {'id': 'c', 'storage_path': 'missing.pdf', 'payload_bytes': 0},
    ]}, source, objects)
    assert report['blocking_gaps'] == 1
    assert report['source_counts']['payload_present'] == 1
    assert report['source_counts']['local_only_present'] == 1
    assert not report['source_payload_bytes_hashed']


def test_nested_preview_album_and_derived_objects(roots):
    source, objects = roots
    (objects / 'bucket').mkdir()
    (objects / 'bucket' / 'a').write_bytes(b'a')
    (objects / 'bucket' / 'derived').write_bytes(b'd')
    data = {'artifacts': [{'id': 'a', 'storage_uri': 's3://bucket/a', 'metadata': {
        'telegram_album': {'artifact_ids': ['a', 'missing']},
        'album_preview': [{'storage_uri': 's3://bucket/preview'}],
        'telegram_live_photo': {'photo_id': 'a', 'video_id': 'missing-video'},
        'url': 'https://example.invalid/private?token=secret'}}],
        'platform_copy_media': [{'storage_uri': 's3://bucket/derived', 'sha256': hashlib.sha256(b'd').hexdigest()}]}
    report = module.coverage(data, source, objects)
    assert report['object_count'] == 3
    assert report['blocking_gaps'] == 3
    assert len(report['missing_child_record_ids']) == 2
    assert 'present_hash_verified' in [r['state'] for r in report['objects']]
    assert 'secret' not in str(report)
    assert 'bucket' not in str(report)
    assert not report['live_inventory_verified']
    assert not report['durable_backup_created']


@pytest.mark.parametrize('key', ['../escape', '%2e%2e/escape', 'a/../../escape', 'x?secret=y', 'x#fragment', 'a\\b'])
def test_invalid_object_keys(roots, key):
    source, objects = roots
    report = module.coverage({'artifacts': [{'id': 'a', 'storage_uri': 's3://bucket/' + key}]}, source, objects)
    assert report['objects'][0]['state'] == 'invalid_reference'


def test_symlink_and_local_escape(roots, tmp_path):
    source, objects = roots
    outside = tmp_path / 'secret'
    outside.write_bytes(b'secret')
    (source / 'link').symlink_to(outside)
    (objects / 'bucket').symlink_to(tmp_path, target_is_directory=True)
    report = module.coverage({'sources': [{'id': 'a', 'storage_path': 'link'}, {'id': 'b', 'storage_path': '../secret'}],
                              'artifacts': [{'id': 'a', 'storage_uri': 's3://bucket/secret'}]}, source, objects)
    assert report['blocking_gaps'] == 3


def test_hash_mismatch_and_empty(roots):
    source, objects = roots
    (objects / 'bucket').mkdir()
    (objects / 'bucket' / 'a').write_bytes(b'corrupted')
    (objects / 'bucket' / 'empty').touch()
    report = module.coverage({'platform_copy_media': [
        {'storage_uri': 's3://bucket/a', 'sha256': '0' * 64},
        {'storage_uri': 's3://bucket/empty'}]}, source, objects)
    assert report['blocking_gaps'] == 2
    assert {o['state'] for o in report['objects']} == {'hash_mismatch', 'empty_object'}


def test_source_object_reference(roots):
    source, objects = roots
    report = module.coverage({'sources': [{'id': 'a', 'storage_path': 's3://bucket/a', 'payload_bytes': 0}]}, source, objects)
    assert report['object_count'] == 1
    assert report['source_counts']['object_reference'] == 1
    assert report['blocking_gaps'] == 1


def test_empty_input_never_claims_complete(roots):
    report = module.coverage({}, *roots)
    assert not report['input_has_rows']
    assert not report['live_inventory_verified']


@pytest.mark.parametrize('length', [-1, True, '3'])
def test_invalid_lengths_rejected(roots, length):
    with pytest.raises(ValueError):
        module.coverage({'sources': [{'payload_bytes': length}]}, *roots)


def test_inline_text_requires_actual_database_text_evidence(roots):
    report = module.coverage({'sources': [
        {'id': 'a', 'storage_path': 'inline://a', 'database_text_bytes': 5},
        {'id': 'b', 'storage_path': 'manual-draft', 'database_text_bytes': 3},
        {'id': 'c', 'storage_path': 'inline://c'},
        {'id': 'd', 'storage_path': 'missing.pdf', 'database_text_bytes': 10},
    ]}, *roots)
    assert report['source_counts']['database_text_present'] == 2
    assert report['blocking_gaps'] == 2


def test_unsupported_remote_storage_and_local_artifact(roots):
    source, objects = roots
    (source / 'file').write_bytes(b'local')
    report = module.coverage({'artifacts': [
        {'id': 'a', 'storage_uri': 'https://example.invalid/media?token=secret'},
        {'id': 'b', 'storage_uri': 'file'},
    ]}, source, objects)
    assert report['blocking_gaps'] == 1
    assert {o['state'] for o in report['objects']} == {'invalid_reference', 'present_hash_unavailable'}
    assert 'secret' not in str(report)
