"""Destructive recovery drill for disposable LOOPBACK databases only.

Not a live backup tool. Requires pg_dump/pg_restore/psql matching the server.
No application server, scheduler, provider or cloud storage calls are started.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tarfile
import tempfile
from urllib.parse import urlsplit, unquote


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate_url(value):
    p = urlsplit(value)
    if p.scheme != 'postgresql' or p.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Only explicit loopback PostgreSQL URLs are allowed.')
    if re.fullmatch(r'/recovery_drill_[A-Za-z0-9_]+', unquote(p.path)) is None or p.query or p.fragment:
        raise ValueError('Database name must start recovery_drill_; URL options are not allowed.')
    return value


def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('Symlinks are not allowed in drill fixtures.')
        if p.is_file():
            result[p.relative_to(root).as_posix()] = {'bytes': p.stat().st_size, 'sha256': digest(p)}
    if not result:
        raise ValueError('Fixture file tree must not be empty.')
    return result


def check_manifest(root, expected):
    if inventory(root) != expected:
        raise ValueError('File manifest mismatch: missing, extra or changed bytes.')


def run(binary, args, *, env):
    # Do not echo commands, URLs or subprocess stderr, which can contain secrets.
    result = subprocess.run([binary, *args], env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{Path(binary).name} failed with exit {result.returncode}; no success recorded.')
    return result.stdout


def connection(url):
    p = urlsplit(url)
    env = {**os.environ}
    env.update(PGHOST=p.hostname, PGPORT=str(p.port or 5432), PGUSER=unquote(p.username or ''),
               PGPASSWORD=unquote(p.password or ''), PGDATABASE=unquote(p.path[1:]), PGCONNECT_TIMEOUT='5')
    # Prevent inherited service/options overriding this isolated connection.
    for key in ['PGSERVICE', 'PGSERVICEFILE', 'PGOPTIONS', 'PGHOSTADDR', 'PGPASSFILE']:
        env.pop(key, None)
    return env


def sql(bin_dir, env, query):
    return run(str(bin_dir / 'psql'), ['-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-c', query], env=env).strip()


def snapshot(bin_dir, env):
    tables = json.loads(sql(bin_dir, env, "SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public'"))
    result = {}
    for name in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        rows = sql(bin_dir, env, f'SELECT coalesce(json_agg(v ORDER BY v::text),\'[]\') FROM (SELECT to_jsonb(t) v FROM public.{quoted} t) s')
        values = json.loads(rows)
        canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        result[name] = {'rows': len(values), 'sha256': hashlib.sha256(canonical).hexdigest()}
    return result


def drill(source, target, fixture_root, bin_dir, output):
    validate_url(source)
    validate_url(target)
    if source == target:
        raise ValueError('Source and target must differ.')
    source_env, target_env = connection(source), connection(target)
    if (source_env['PGPORT'], source_env['PGDATABASE']) == (target_env['PGPORT'], target_env['PGDATABASE']):
        raise ValueError('Source and target must be different loopback databases.')
    if sql(bin_dir, target_env, "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')") != '0':
        raise ValueError('Restore target is not empty; refused.')
    if fixture_root.is_symlink():
        raise ValueError('Fixture root cannot be a symlink.')
    files = inventory(fixture_root)
    before = snapshot(bin_dir, source_env)
    if not before:
        raise ValueError('Source has no public tables.')
    with tempfile.TemporaryDirectory(prefix='nashr-isolated-drill-') as tmp:
        root = Path(tmp)
        dump = root / 'database.dump'
        run(str(bin_dir / 'pg_dump'), ['--format=custom', '--no-owner', '--no-acl', '--file', str(dump)], env=source_env)
        os.chmod(dump, 0o600)
        # Synthetic fixtures only. Real archives need separately approved encryption/key retention.
        archive = root / 'files.tar'
        with tarfile.open(archive, 'w') as tar:
            for name in files:
                tar.add(fixture_root / name, arcname=name, recursive=False)
        restored = root / 'restored-files'
        restored.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                path = Path(member.name)
                if not member.isfile() or path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unsafe archive member.')
                dest = restored / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, dest.open('wb') as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b''):
                        dst.write(chunk)
        check_manifest(restored, files)
        run(str(bin_dir / 'pg_restore'), ['--exit-on-error', '--no-owner', '--no-acl', '--dbname', target_env['PGDATABASE'], str(dump)], env=target_env)
        after = snapshot(bin_dir, target_env)
        if before != after:
            raise ValueError('Restored table rows differ from source.')
        # Demonstrate corruption is a failure, not a green result.
        first = restored / next(iter(files))
        with first.open('ab') as stream:
            stream.write(b'CORRUPTION')
        try:
            check_manifest(restored, files)
        except ValueError:
            corruption_detected = True
        else:
            raise AssertionError('Corruption was not detected.')
        source_unchanged = before == snapshot(bin_dir, source_env)
        if not source_unchanged:
            raise ValueError('Source changed during drill; comparison is not a stable recovery proof.')
        report = {'scope': 'SYNTHETIC_LOOPBACK_ONLY', 'source_database_unchanged': source_unchanged,
                  'database_round_trip': before == after, 'tables': after, 'files': files,
                  'database_dump_bytes': dump.stat().st_size, 'database_dump_sha256': digest(dump),
                  'file_archive_bytes': archive.stat().st_size, 'file_round_trip': True,
                  'corruption_detected': corruption_detected, 'live_backup_created': False,
                  'durable_destination_verified': False, 'provider_credentials_tested': False}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'scope': report['scope'], 'tables': len(after), 'rows': sum(x['rows'] for x in after.values()),
                      'files': len(files), 'database_round_trip': True, 'file_round_trip': True,
                      'corruption_detected': True, 'live_backup_created': False}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-url-env', default='RECOVERY_DRILL_SOURCE_URL')
    parser.add_argument('--target-url-env', default='RECOVERY_DRILL_TARGET_URL')
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--pg-bin', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    drill(os.environ[args.source_url_env], os.environ[args.target_url_env], args.fixtures, args.pg_bin, args.report)


if __name__ == '__main__':
    main()
