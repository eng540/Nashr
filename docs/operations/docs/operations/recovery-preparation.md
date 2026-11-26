# Nashr recovery preparation

Status: isolated recovery drill passed on 26 November 2026. No live backup exists as a result of this drill.

## Evidence and scope

Code baseline: main `0b3dfff97bb03556a8360a1dabf1663310e715a2`.

A fresh disposable PostgreSQL 16 database was migrated to the current schema. It contained migration-seeded definitions plus synthetic source, knowledge-unit, approved post, media reference, publication result and completed plan fixtures. A custom-format dump was restored into a second empty database. All 63 public tables, totalling 97 rows, matched by full-row canonical hashes. Two synthetic files matched after archive recovery. Intentional file corruption was detected; a second restore into the nonempty target was refused. The source database remained unchanged.

PDF recovery from the restored `sources.file_payload` was checked through `SourceModel.ensure_file_on_disk`. A legacy source without both payload and local file correctly failed. This does not establish whether current live source rows all have payloads.

Not tested: a live export, live object-store inventory/download, a real S3 restore, production credential decryption, a running restored application, provider validity, external media URLs or performance at live library size. No application server or scheduler was started. Reports retain no connection URLs or credentials. Temporary fixture databases, dump and archives were removed.

## What must be recovered together

- PostgreSQL: originals, review decisions, per-platform copy, media references, product versions, plans, idempotency records and publication history. Preserve completed/published status and external IDs, not only content.
- Source PDFs: binary payloads already in PostgreSQL can recreate local files. Inventory rows lacking payloads and preserve any local-only originals separately. Preserve or deliberately remap storage paths in an isolated environment.
- Private object storage: preserve every referenced object and its original key, metadata, size and a verified content hash. Include album members, previews and derivatives, not only top-level media references. A list of keys is not a backup of the bytes. A bucket on the same provider/account is not independent recovery.
- Configuration and secrets: database connection, bucket settings, app/provider credentials and `NASHR_CONNECTION_ENCRYPTION_KEY` need separately protected recovery and retention. A database containing encrypted connection tokens is unusable for those tokens if the encryption key is lost. Never put credentials, keys, `.env`, auth cookies or signed media URLs into a report, source control or ordinary archive.
- Application version and tools: retain the exact source revision and migration head with the backup. Use a compatible PostgreSQL client; the available system pg_dump14 cannot dump a PostgreSQL16 server. This drill used the matching16 tools. This does not establish the live server version.

## Safe live backup sequence, not executed

1. Establish an approved private, durable encrypted destination, retention policy and independent key custody. Confirm provider costs before activating a paid service. Verify destination quota, provider tier requirements and cost live before choosing a destination. Nothing here approves spending or changing accounts.
2. Inventory source payload coverage and all local/S3 references read-only. Define a consistent cutoff. Coordinate a brief write pause or otherwise establish consistency across database and objects. A PostgreSQL snapshot alone does not freeze object storage. Do not delete or move originals.
3. Export PostgreSQL in custom format with compatible tools and no ownership/ACL dependence. Make a manifest of revision, migration head, UTC cutoff, table counts, file keys, sizes and hashes. Credentials must be passed through protected execution configuration, not command history or logs.
4. Export source files not safely represented in the DB and every required object using bounded reads. Verify exported bytes against the manifest. Encrypt before sending to the agreed destination. Verify upload completeness and a fresh download/decryption, not only upload success.
5. Restore only into an empty isolated database and private isolated media location. Block outbound provider traffic and automatic jobs. Restored queued work must not be allowed to run during the drill. Compare rows, relationships, hashes and media paths; check original/review/per-platform copy separately.
6. Test read-only application views and media access in isolation. Verify decryption availability without exposing secrets. Tokens may have expired independently of recovery. A successful restore must not resend a completed publication.
7. Only after evidence passes, record a live backup and its restore checkpoint. A production switch, change in destination, or resumption of queued work needs a separate reviewed plan. Never restore over the running database as a test.

## Reusable isolated drill

`scripts/recovery_drill.py` accepts only explicit loopback PostgreSQL URLs whose database names begin `recovery_drill_`, rejects URL options, and refuses a nonempty target. Use synthetic data only. It does not encrypt, upload, export S3, start the application, remap paths or certify live inventory completeness. Its files archive is plaintext and temporary, suitable for synthetic fixtures only.

Inputs are environment variable names holding source and target URLs, a directory of synthetic file fixtures, an explicit directory of matching PostgreSQL binaries and an output report path. The drill fails on any dump/restore error, table mismatch, unsafe archive path, symlink or hash mismatch. A green JSON report is emitted only after database/file comparisons and intentional corruption detection pass.

Run the reproducible synthetic fixture harness with the project test dependencies installed:

```sh
python scripts/recovery_drill_fixture.py --pg-bin /path/to/postgresql16/bin --report-dir /private/report-directory
pytest tests/unit/test_recovery_drill.py -q
```

It initializes a fresh trust-authenticated server bound to loopback on an available port, creates both disposable databases, applies current migrations and seeds synthetic content. Run only on a trusted isolated host with no untrusted local users. It stops the server and removes temporary databases and file archives in its cleanup path. Only proof reports are retained. No production connection input is accepted by this fixture harness.

Reports: `round-trip.json`, `semantic-checks.json`, `safety-checks.json`; `migration.log` records only the fresh isolated schema migration.

## Remaining dependency

This package contains preparation and synthetic proof, not a copy of a live library. Live completeness, a durable encrypted destination, retention/cost choice, key recovery and a real isolated restore remain unresolved. Do not label these reports as a live backup or claim a recovery-point/recovery-time objective from this small drill.
