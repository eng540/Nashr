import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('export_inventory', Path(__file__).parents[2] / 'scripts/recovery_inventory_export.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample():
    return {'sources': [{'id': 's', 'payload_bytes': 12}],
            'artifacts': [{'id': 'a', 'storage_uri': 's3://bucket/a', 'metadata': {
                'references': ['s3://bucket/preview', 'https://example.invalid/media'],
                'artifact_ids': ['a', 'child']}}],
            'platform_copy_media': [],
            'snapshot': {'source_rows': 1, 'artifact_rows': 1, 'derivative_rows': 0}}


def test_reduced_reference_shape():
    result = module.finalize(sample())
    assert result['artifacts'][0]['metadata'] == {
        'storage_references': [{'storage_uri': 's3://bucket/preview'}, {'storage_uri': 'https://example.invalid/media'}],
        'artifact_ids': ['a', 'child']}
    assert result['export_evidence']['content_bodies_exported'] is False
    assert len(result['export_evidence']['reduced_inventory_sha256']) == 64


def test_count_mismatch_fails():
    data = sample()
    data['snapshot']['source_rows'] = 2
    with pytest.raises(ValueError):
        module.finalize(data)


def test_duplicate_ids_fail():
    data = sample()
    data['sources'] *= 2
    data['snapshot']['source_rows'] = 2
    with pytest.raises(ValueError):
        module.finalize(data)


def test_query_selects_no_secret_or_content_bodies():
    assert 'resolved_context' not in module.QUERY
    assert 'review_note' not in module.QUERY
    assert 'connections' not in module.QUERY
    assert 'octet_length' in module.QUERY
    assert 'jsonb_path_query_array' in module.QUERY


def test_non_loopback_refused_before_database_access(tmp_path):
    with pytest.raises(ValueError):
        module.export('postgresql://example.invalid/recovery_drill_test', tmp_path, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()
