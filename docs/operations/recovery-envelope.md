# Offline encrypted recovery envelope

This tool is preparation, not a backup service. It performs no database, network,
provider, upload, retention or key-generation operation. No live library has been
backed up by its synthetic tests.

`scripts/recovery_envelope.py` wraps a local recovery package with standard
OpenSSL CMS AuthEnvelopedData, AES-256-GCM and a supplied recipient certificate.
Only the public certificate is needed at the backup host. The corresponding
private key must be held separately under an approved recovery arrangement.
Never reuse the Nashr connection-encryption key for this purpose. Never put a
private key or passphrase in source control, logs, a report or the backup itself.
The wrapper does not establish that a supplied key/certificate belongs to the
intended recovery owner, remains accessible, or is securely retained.

## Preconditions before real use

- An approved private durable destination with sufficient quota and no new cost
  outside the user's authority. A temporary download or same-account snapshot
  is not independent durable recovery.
- Independently recoverable key custody, including a tested way for the owner to
  recover the private key if the original app/provider account is unavailable.
- A complete consistent source package and trusted SHA256, with exact app
  revision, migration head, UTC cutoff, source/object inventory and hashes.
  Encryption does not establish inventory completeness or snapshot consistency.
- A private trusted local host and staging directory with space for input plus
  tentative output. Symlink input files are refused; parent directories and
  local processes remain trusted. OpenSSL must support CMS AES-256-GCM and the
  supplied recipient certificate. Synthetic proof used OpenSSL3.0.2/RSA3072.

## Commands

```sh
python scripts/recovery_envelope.py encrypt \
  --source /private/recovery-package.tar \
  --destination /private/recovery-package.cms \
  --certificate /private/approved-recipient.crt

python scripts/recovery_envelope.py decrypt \
  --source /private/downloaded-package.cms \
  --destination /private/verified-package.tar \
  --certificate /private/approved-recipient.crt \
  --private-key /private/recovery-recipient.key \
  --expected-sha256 TRUSTED_ORIGINAL_PACKAGE_SHA256
```

For an encrypted private key, `--passphrase-env VARIABLE_NAME` accepts the name
of a protected environment variable, never its value. Without it, interactive
password prompts are disabled. A wrong key/password, authentication failure or
trusted-digest mismatch fails closed and publishes no final output. Output
must not already exist. The verified staged file is published atomically by a
same-filesystem hard link with mode0600, refusing an existing destination.
Filesystems without hard-link support fail rather than downgrade to a partial
copy. No automatic deletion of the original input or older recovery packages.

OpenSSL may emit tentative plaintext before reporting authentication failure.
The wrapper keeps it in a private temporary directory and discards it unless
OpenSSL exits zero AND the trusted original SHA256 matches. Never pipe raw
OpenSSL decryption straight into `pg_restore` or an archive extractor. A digest
supplied beside an untrusted archive is not an independently trusted digest.
Authenticated encryption to a public recipient certificate alone does not
prove the sender's identity; an attacker who knows that certificate can encrypt
a replacement. Preserve the trusted original digest separately.

After decrypting, follow `recovery-preparation.md`: inspect archive paths, restore
only into an empty isolated DB/media location with outbound jobs blocked, compare
rows/relationships/media hashes and do not resend completed publications. Passing
this wrapper does not authorize a production restore or restore target switch.

## Verified preparation and current constraints

On26November2026 a1.15MB synthetic package round-tripped using OpenSSL3.0.2,
RSA3072 and AES256GCM. Wrong-key and modified-authentication-tag cases failed.
All temporary synthetic keys and archives were removed. Unit tests also cover
wrong expected digest, symlink inputs, existing output and temporary cleanup.

No destination, retention schedule, deletion policy or key custody decision is
created by this document. Do not call a live backup complete until independent
upload, fresh download, decryption and isolated restore acceptance all pass.
