import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('recovery_drill', Path(__file__).resolve().parents[2] / 'scripts/recovery_drill.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize('url', [
    'postgresql://user@remote.example/recovery_drill_a',
    'postgresql://user@127.0.0.1/production',
    'postgresql://user@localhost/recovery_drill_a?host=remote.example',
    'postgresql://user@localhost/recovery_drill_a#options',
    'postgres://user@localhost/recovery_drill_a',
    'postgresql://user@localhost/%70roduction',
    'postgresql://user@localhost/recovery_drill_a/../production',
])
def test_unsafe_database_rejected(url):
    with pytest.raises(ValueError):
        m.validate_url(url)


@pytest.mark.parametrize('host', ['127.0.0.1', 'localhost', '[::1]'])
def test_loopback_disposable_database_allowed(host):
    url = f'postgresql://user@{host}:5432/recovery_drill_a'
    assert m.validate_url(url) == url


def test_manifest_detects_changed_missing_and_extra_files(tmp_path):
    p = tmp_path / 'fixture.bin'
    p.write_bytes(b'original')
    expected = m.inventory(tmp_path)
    m.check_manifest(tmp_path, expected)
    p.write_bytes(b'changed')
    with pytest.raises(ValueError):
        m.check_manifest(tmp_path, expected)
    p.unlink()
    with pytest.raises(ValueError):
        m.check_manifest(tmp_path, expected)
    p.write_bytes(b'original')
    (tmp_path / 'extra').write_bytes(b'x')
    with pytest.raises(ValueError):
        m.check_manifest(tmp_path, expected)


def test_manifest_refuses_symlink(tmp_path):
    (tmp_path / 'data').write_bytes(b'data')
    (tmp_path / 'link').symlink_to(tmp_path / 'data')
    with pytest.raises(ValueError):
        m.inventory(tmp_path)


def test_connection_removes_inherited_overrides(monkeypatch):
    monkeypatch.setenv('PGSERVICE', 'production')
    monkeypatch.setenv('PGOPTIONS', '-c search_path=elsewhere')
    env = m.connection('postgresql://synthetic@127.0.0.1:5439/recovery_drill_a')
    assert env['PGDATABASE'] == 'recovery_drill_a'
    assert env['PGHOST'] == '127.0.0.1'
    assert env['PGPORT'] == '5439'
    assert 'PGSERVICE' not in env and 'PGOPTIONS' not in env


def test_failure_does_not_echo_subprocess_stderr(monkeypatch):
    class Failed:
        returncode = 1
        stdout = ''
        stderr = 'private diagnostic'
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: Failed())
    with pytest.raises(RuntimeError) as error:
        m.run('pg_dump', [], env={})
    assert 'private diagnostic' not in str(error.value)
