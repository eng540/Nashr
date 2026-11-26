"""Read-only reduced inventory from an ISOLATED loopback recovery database.

Not a production exporter. No account/token/config tables or text bodies are
selected. Output contains private storage references and must remain private.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.recovery_drill import connection, sql, validate_url


QUERY = """
SELECT json_build_object(
  'sources', coalesce((SELECT json_agg(json_build_object(
    'id', s.id, 'storage_path', s.storage_path,
    'payload_bytes', coalesce(octet_length(s.file_payload),0),
    'database_text_bytes', coalesce((SELECT sum(octet_length(coalesce(nullif(k.original_text,''),k.content,'')))
      FROM knowledge_units k WHERE k.source_id=s.id),0)
  ) ORDER BY s.id) FROM sources s),'[]'::json),
  'artifacts', coalesce((SELECT json_agg(json_build_object(
    'id', a.id, 'storage_uri', a.storage_uri, 'metadata', jsonb_build_object(
      'references', jsonb_path_query_array(coalesce(a.metadata,'{}'::jsonb), '$.**.storage_uri')
        || jsonb_path_query_array(coalesce(a.metadata,'{}'::jsonb), '$.**.storage_path')
        || jsonb_path_query_array(coalesce(a.metadata,'{}'::jsonb), '$.** ? (@.type() == "string" && @ like_regex "^s3://")'),
      'artifact_ids', jsonb_path_query_array(coalesce(a.metadata,'{}'::jsonb), '$.**.artifact_ids[*]')
        || jsonb_path_query_array(coalesce(a.metadata,'{}'::jsonb), '$.**.photo_id')
        || jsonb_path_query_array(coalesce(a.metadata,'{}'::jsonb), '$.**.video_id'))
  ) ORDER BY a.id) FROM artifacts a),'[]'::json),
  'platform_copy_media', coalesce((SELECT json_agg(json_build_object(
    'id', m.id, 'storage_uri', m.storage_uri, 'sha256', m.sha256
  ) ORDER BY m.id) FROM platform_copy_media m),'[]'::json),
  'snapshot', json_build_object('transaction_snapshot', txid_current_snapshot()::text,
    'source_rows', (SELECT count(*) FROM sources),
    'artifact_rows', (SELECT count(*) FROM artifacts),
    'derivative_rows', (SELECT count(*) FROM platform_copy_media))
)
"""


def finalize(data):
    counts = data['snapshot']
    for name, count_key in [('sources','source_rows'), ('artifacts','artifact_rows'), ('platform_copy_media','derivative_rows')]:
        rows = data[name]
        if len(rows) != counts[count_key] or len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Inventory row count or identity mismatch.')
    for artifact in data['artifacts']:
        raw = artifact.get('metadata') or {}
        refs = raw.get('references', [])
        artifact['metadata'] = {
            'storage_references': [{'storage_uri': v} for v in refs if isinstance(v, str)],
            'artifact_ids': [v for v in raw.get('artifact_ids', []) if isinstance(v, str)],
        }
    content = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return {**data, 'export_evidence': {'reduced_inventory_sha256': hashlib.sha256(content).hexdigest(),
            'database_access': 'loopback_read_only_single_statement',
            'live_production_export': False, 'account_tables_selected': False,
            'content_bodies_exported': False}}


def export(url, bin_dir, output):
    validate_url(url)
    env = connection(url)
    # Enforced by PostgreSQL, even if the query is accidentally changed later.
    env['PGOPTIONS'] = '-c default_transaction_read_only=on -c statement_timeout=30000'
    data = finalize(json.loads(sql(bin_dir, env, QUERY)))
    # Exclusive create prevents replacing an input, original or prior evidence.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url-env', required=True)
    parser.add_argument('--pg-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = export(os.environ[args.database_url_env], args.pg_bin, args.output)
    print(json.dumps({'snapshot': result['snapshot'], 'export_evidence': result['export_evidence']}))


if __name__ == '__main__':
    main()
