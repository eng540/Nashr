# Offline recovery coverage inventory

This companion to `recovery_drill.py` checks a reduced inventory against an
**isolated copy** of source files and object bytes. It never connects to a DB,
S3, an AI provider, or a publishing service. It does not create a backup.

## Input contract

Prepare the JSON privately from an independently verified isolated DB export.
Do not pass full database rows, credentials, account configuration, post bodies,
or access tokens. The checker consumes only these fields:

- `sources`: `id`, `storage_path`, `payload_bytes` (the actual byte length of
  `file_payload`, not the payload itself). For `inline://...` and `manual-draft`
  sources also supply `database_text_bytes`: the verified byte length of their
  linked Knowledge Unit `original_text`/`content`. Do not infer this from
  `sources.size_bytes`. Without actual text evidence these remain gaps.
- `artifacts`: `id`, `storage_uri`, optional `sha256`, and `metadata` (map the
  database column `artifact_metadata` to `metadata`). Include all artifacts,
  including unapproved/excluded/historical records. Do not export only rows
  currently visible in the bank UI.
- `platform_copy_media`: `id`, `storage_uri`, `sha256`. Include unselected and
  historical derivatives, not only the current selected copy.

## Isolated database exporter

`scripts/recovery_inventory_export.py` now prepares this reduced input from a
restored loopback database named `recovery_drill_*`. It runs one SELECT with
PostgreSQL read-only mode enforced, selects no account/config/token tables,
and emits no text bodies. JSON paths select only storage/child references from
artifact metadata. The snapshot records source/artifact/derivative row counts,
transaction snapshot and a digest of the reduced inventory. Counts cover those
three queried tables, not an assertion that every application relationship or
provider capability is backed up. This is not a production export command.

```sh
# ISOLATED_URL holds the disposable restored loopback PostgreSQL URL.
python scripts/recovery_inventory_export.py \
  --database-url-env ISOLATED_URL \
  --pg-bin /path/to/matching/postgresql/bin \
  --output /private/isolated-inventory.json
```

Output is created exclusively with mode0600; existing paths are refused. Storage
references and record IDs remain private even though text bodies are omitted.
Keep output in an approved private location. The exporter does not copy object
bytes, decrypt tokens, follow HTTP URLs, or contact providers. Absolute historical
source paths still need an explicit offline mapping before coverage can pass.
The fixture harness tests this exporter on the fresh migrated/restored synthetic
schema, checks counts and output permissions, detects missing copied media,
rejects overwrites and verifies PostgreSQL refuses writes in read-only mode.

Independent source-to-export row
counts, snapshot identity and database-table completeness must be established
before using this tool to assess a real recovery. An empty/partial input cannot
certify coverage. Metadata can contain private references, so keep input private.
The report emits hashed identifiers rather than raw storage paths/URLs.

Place S3 copies under `OBJECT_ROOT/<bucket>/<key>`. Place relative source/local
artifact paths under `SOURCE_ROOT`; absolute paths are accepted only when they
are already inside that root. If historical absolute paths refer elsewhere,
report them as missing until an explicit offline mapping/export is implemented.
No searching the host filesystem or provider fallback occurs.

```sh
python scripts/recovery_coverage.py \
  --inventory /private/isolated-inventory.json \
  --source-root /private/isolated-files \
  --object-root /private/isolated-objects \
  --report /private/coverage-report.json
```

The command exits 2 for known gaps or empty input, 0 for no detected gaps in a
nonempty input. Exit 0 **does not mean complete backup or verified restore**.
Invalid input/I/O errors fail nonzero, never success. Reports are ordinary local
files, not encrypted archives. Keep input and reports in an approved private
location and do not overwrite original evidence with the output path.

## Coverage and limits

- A source with positive payload length is counted as payload-present. This
  does not hash, decode or validate those bytes. The isolated restore drill
  separately checks payload rehydration on synthetic fixtures.
- Sources without payload must have a local copy or a copied S3 object.
  Database-only inline/manual sources require positive linked text evidence.
- Original artifact storage references, nested metadata references (including
  album/Live Photo preview snapshots), and derivative storage references are
  deduplicated. Arbitrary nested S3 strings are included. Unsupported remote
  storage references fail closed; ordinary external HTTP links in other
  metadata fields are not recovered or validated.
- Album `artifact_ids` and Live Photo `photo_id`/`video_id` links are checked for
  child record presence. This does not reapprove their content, validate every
  application relationship, or rerun publication readiness.
- Missing, empty, malformed and escaping object references are gaps. Symlink
  roots/parents/leaves and path traversal are rejected. Trusted supplied
  derivative/object hashes are checked; absence of an expected hash remains
  explicitly unverified, not silently hash-verified.
- Object orphans, third-party file IDs, presigned URL renewal, provider access,
  database constraints, credentials, encryption, retention, key custody and
  live database/storage inventory are outside this checker. It is not a
  substitute for the complete restore acceptance runbook.

## Acceptance

Run `pytest tests/unit/test_recovery_coverage.py tests/unit/test_recovery_drill.py`.
Use synthetic fixtures. No production DB export, S3 read, scheduler or publisher
needs to run for this bounded tool's tests.
