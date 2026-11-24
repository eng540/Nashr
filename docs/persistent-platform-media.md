# Private media for a platform copy

2026-11-24. Additive migration 0058, no changes to original Artifact, imported Source, old schedules or publications.

## User flow

1. Open an approved original and its Instagram copy.
2. Choose the background and review the temporary JPEG preview.
3. Explicitly save and select that exact preview for this platform. The submitted SHA-256 must match a freshly generated result, so reviewed bytes cannot be silently substituted.
4. The immutable private derivative record stores original fingerprint/hash, output hash, recipe, dimensions and creation time. The platform copy points to it, and its version increases. Text fields and other platform copies do not change.
5. Reload saved media, view it through a 5-minute signed URL, inspect actual selected bytes, switch between current derivatives, or explicitly return to the original. Old media remains history, not bank originals.

Changed original content, caption, status, file URI or metadata produces a stale fingerprint. A stale derivative can be reviewed as history but cannot be selected or pass selected-byte inspection. A stale copy can return to original without silently reaccepting its edited fields; those retain their independent stale warning until reviewed.

The saved media is not publication approval. This release deliberately leaves Telegram execution and prior schedule contracts untouched and offers no Telegram derivative selection. Non-Telegram execution still requires a connector, account permissions, media acceptance, destination and separate user authority.

## Concurrency and failure

Original and copy rows are locked in that order before bounded reading/conversion/upload. Copy version and original fingerprint must match. A second save at the old version fails instead of replacing a newer choice. Identical source/hash/recipe reuses the existing derivative object; an ambiguous client retry must reload the newer copy version.

Storage failure occurs before selection and database commit, leaving selection/version intact. A database commit error after object upload is ambiguous: bytes are retained privately for reconciliation, never deleted on the assumption the commit failed. This avoids deleting an object that a successful-but-unacknowledged commit selected. Such errors are logged, no success is reported. There is no automatic purge of old versions in this release. Recent history is bounded to 30 plus the current selected record.

Fresh LittleCMS profiles included wall-clock creation time, so we normalize only that ICC header to 2000-01-01. Without this, identical preview/save recipes would hash differently across time. Tests cover determinism without changing the actual color profile matrices or source metadata policy.

## Verification

Real PNG → JPEG; read-only preview; explicit hash-confirmed persistence; no original/fields/other-copy/schedule/publication mutation; private link; selected-byte probe; old-version rejection; cross-platform rejection; source staleness and recovery; failed storage; concurrent same-version saves; migration up/down/up on isolated database. Browser checks mobile and desktop, actual saved-selection rendering, private preview and return to original.

Limits are unchanged: no crop, no AI, no animated flattening, quality90, bounded pixels/bytes, explicit background, no public media URL. No complete video conversion or Instagram publishing connector is claimed.
