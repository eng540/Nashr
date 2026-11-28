# Dormant private-child provenance boundary

`instagram_private_child_resolver.resolve` takes only the exact preparation ID,
parent review ID and saved snapshot hash. Persisted receipts select all child
IDs and their order. It locks parent, receipt, execution drafts and saved child
reviews with NOWAIT, validates their exact immutable snapshot digests, both-way
ownership and the complete owned-child set. Words, account, media inspection,
feed choice, source/copy pins, connection identity digest, time and timezone must
match the saved parent and each other. Missing, foreign, reordered, duplicate,
malformed, cancelled or non-DRAFT children fail closed. No private account token
or connection binding is returned.

This is a provenance reader, not execution or Stop authority. Its transaction
ends on return. It does not assert current source/copy/selection/account/media
validity, byte validity, decision/grant validity, runnable dispatch identity or
owner consent. It creates no isolated controls and does not bridge synthetic
controls to real dispatches. PRIVATE_BATCH_UNIFIED remains incompatible with
individual or atomic approval. No module consumer, route, scheduler or provider
operation is added. The accepted isolated claim protocol is unchanged.

## Activation gates still open

- A transaction-scoped production resolver, used inside each claim/Stop command,
  that links persisted exact batch, child, real dispatch, decision and grant rows.
- Separate authenticated exact approval and media-disclosure authority, plus
  fresh account/source/copy/selection/inspection/byte rechecks before activation.
- Shared production fence across individual execution, batch runtime and media
  resume, with separate forever-unique CREATE/PUBLISH claims and no unknown replay.
- Batch/item Stop commands using that same fence, exact frozen scope, immutable
  receipts and truthful in-flight acknowledgement, never synthetic client IDs.
- Read-only reconciliation with durable backoff and stale-read suppression.
- Real Stop UI and per-item outcomes, independently inspected at390/1280.
- Verified supervisor attestation and audited recovery, or recovery unavailable.

This delta closes only private draft provenance mapping, not those gates.
