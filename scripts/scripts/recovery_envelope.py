"""Offline authenticated envelope for recovery packages, no network or DB calls.

An independent trusted SHA256 is mandatory on decrypt. No key generation or
retention policy is supplied. This does not establish a live backup exists.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Input must be an existing regular non-symlink file.')
    return path


def envelope(mode, source, destination, certificate, *, private_key=None,
             expected_sha256=None, passphrase_env=None, openssl='openssl'):
    source, certificate = regular(source), regular(certificate)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Output already exists; refused.')
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('Output parent must exist.')
    if mode not in {'encrypt', 'decrypt'}:
        raise ValueError('Unsupported mode.')
    args = [openssl, 'cms', '-' + mode, '-binary', '-in', str(source)]
    if mode == 'encrypt':
        args += ['-aes-256-gcm', '-outform', 'DER']
    else:
        private_key = regular(private_key)
        if not expected_sha256 or not re.fullmatch('[0-9a-fA-F]{64}', expected_sha256):
            raise ValueError('Trusted original SHA256 required before decryption.')
        args += ['-inform', 'DER', '-recip', str(certificate), '-inkey', str(private_key)]
        if passphrase_env:
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', passphrase_env) or passphrase_env not in os.environ:
                raise ValueError('Passphrase environment variable is missing or invalid.')
            args += ['-passin', 'env:' + passphrase_env]
        else:
            # Never hang waiting for a password or fall back to interactive input.
            args += ['-passin', 'pass:']
    # OpenSSL can emit unauthenticated plaintext before its final error. Never
    # expose it to a restore pipeline or final destination before both checks.
    with tempfile.TemporaryDirectory(prefix='.nashr-envelope-', dir=parent) as temp:
        staged = Path(temp) / 'staged'
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        command = args + ['-out', str(staged)]
        if mode == 'encrypt':
            command.append(str(certificate))
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=3600)
        if result.returncode:
            raise RuntimeError('Encryption/decryption failed; no output committed.')
        digest = sha256(staged)
        if mode == 'decrypt' and digest.lower() != expected_sha256.lower():
            raise ValueError('Recovered bytes do not match trusted original SHA256.')
        # Staging is on the same filesystem. Hard-link publication is atomic,
        # refuses existing paths and never exposes a partly copied final file.
        with staged.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(staged, destination)
    return {'mode': mode, 'bytes': destination.stat().st_size, 'sha256': digest,
            'live_backup_created': False, 'durable_destination_verified': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['encrypt', 'decrypt'])
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--certificate', type=Path, required=True)
    p.add_argument('--private-key', type=Path)
    p.add_argument('--expected-sha256')
    p.add_argument('--passphrase-env')
    a = p.parse_args()
    envelope(a.mode, a.source, a.destination, a.certificate,
             private_key=a.private_key, expected_sha256=a.expected_sha256,
             passphrase_env=a.passphrase_env)
    print('Offline envelope completed. No live backup or destination verified.')


if __name__ == '__main__':
    main()
