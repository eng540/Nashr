import hashlib
import shutil
import subprocess

import pytest

from scripts.recovery_envelope import envelope


@pytest.fixture
def keys(tmp_path):
    if not shutil.which('openssl'):
        pytest.skip('openssl unavailable')
    for name in ['right', 'wrong']:
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(tmp_path / (name + '.key')),
                        '-out', str(tmp_path / (name + '.crt')),
                        '-subj', '/CN=SYNTHETIC-TEST-ONLY', '-days', '1'],
                       check=True, capture_output=True)
    return tmp_path


def test_authenticated_roundtrip_and_rejections(keys):
    p = keys
    source = p / 'synthetic.dump'
    source.write_bytes(b'SYNTHETIC ONLY\0' * 10000)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    encrypted, restored = p / 'archive.cms', p / 'restored.dump'
    envelope('encrypt', source, encrypted, p / 'right.crt')
    envelope('decrypt', encrypted, restored, p / 'right.crt',
             private_key=p / 'right.key', expected_sha256=digest)
    assert restored.read_bytes() == source.read_bytes()
    assert restored.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        envelope('encrypt', source, encrypted, p / 'right.crt')
    for cert, key, expected, error in [
        ('wrong.crt', 'wrong.key', digest, RuntimeError),
        ('right.crt', 'right.key', '0' * 64, ValueError),
    ]:
        with pytest.raises(error):
            envelope('decrypt', encrypted, p / 'rejected', p / cert,
                     private_key=p / key, expected_sha256=expected)
        assert not (p / 'rejected').exists()
    tampered = bytearray(encrypted.read_bytes())
    tampered[-1] ^= 1
    (p / 'tampered').write_bytes(tampered)
    with pytest.raises(RuntimeError):
        envelope('decrypt', p / 'tampered', p / 'rejected', p / 'right.crt',
                 private_key=p / 'right.key', expected_sha256=digest)
    assert not (p / 'rejected').exists()
    assert not list(p.glob('.nashr-envelope-*'))


def test_refuses_missing_digest_and_symlinks(keys):
    p = keys
    (p / 'source').write_bytes(b'synthetic')
    (p / 'link').symlink_to(p / 'source')
    with pytest.raises(ValueError):
        envelope('encrypt', p / 'link', p / 'out', p / 'right.crt')
    with pytest.raises(ValueError):
        envelope('decrypt', p / 'source', p / 'out', p / 'right.crt',
                 private_key=p / 'right.key')
    assert not (p / 'out').exists()
