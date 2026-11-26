# Dormant atomic batch approval core

This patch has no API route, UI, scheduler registration, provider call or public
media grant. It cannot create a real batch through the running application.
The separate Meta worksheet remains read-only and is not wired to this module.

## Scope and transaction boundary

The first adapter supports Instagram Unified IMAGE/VIDEO execution drafts that
already exist and were individually staged. A private DRAFT records exact order,
material IDs, execution IDs, saved platform choices and their version, outgoing
words, media inspection and digest, account/connection/review binding, feed
choice, IANA zone and UTC time. It does not infer a destination, copy or time.
Other selected platforms remain listed in the snapshot, not silently included.

`stage` uses a stable explicit request key. Reusing it for a different ordered
request fails. Reusing it for the same request returns the original immutable
snapshot; this is not a fresh readiness check or consent.

`approve` is an internal function only. Future authenticated routes must obtain
actual approval of the exact batch, public audience and temporary media disclosure.
Boolean parameters do not establish that authority. The caller must start with
an unused session: the coordinator owns its complete transaction.

All rows are validated before any decision or dispatch is inserted. A single
transaction saves all decisions, all dispatches and batch approval. Failure at
any validation, flush or commit rolls everything back. There are no per-item
commits and no calls to the existing individually committing approval helpers.
Approval retries return the original decision IDs without reviving revoked or
cancelled work. APPROVED means an immutable approval receipt, not that all posts
remain runnable, were published, or can be retried.

## Currentness and concurrency

The coordinator locks jobs, originals, copies, destination selections, connection
and saved reviews. IDs use stable ordering. NOWAIT and try-advisory locks fail
closed on contention rather than deadlocking against old single-item lock order.
It refreshes ORM state under lock and rechecks approved/available originals,
copy version and exact words, current saved destinations, selected inspection,
account and review bindings, and the seven-day future time window. Approval also
re-reads private selected bytes and checks the window again before commit.

Any previous decision/dispatch for an operation blocks a new approval. Any other
non-cancelled operation on the same original/account blocks this first adapter,
including failed or uncertain results. No implicit replay or account fallback.

A worker on another database connection cannot see uncommitted partial inserts.
Existing workers still perform their normal due-time validation. No grant is
created by this module.

## Limits and required next work

Atomic database approval is not atomic external publication. Once committed,
Meta may accept an earlier post and reject a later one. The UI must state this
before approval, and later work needs per-item results, stopping/revocation and
uncertain-outcome reconciliation. Never claim all-or-nothing remote publishing.

This patch does not yet remove individual draft staging. It is a tested internal
transaction foundation, not a complete usable batch workflow. Follow-up work:

- A separately reviewed authenticated exact-batch API and approval UI.
- Batch draft preparation without repeated per-item staging, with validation.
- Full history/current-operation presentation before final approval.
- Equivalent transaction-safe Facebook Page TEXT/IMAGE/Reel adapters.
- Telegram, YouTube, TikTok and all other project platforms remain in scope,
  with their own eligibility, disclosure, consent and account constraints.
- Batch cancellation/revocation and operational result presentation.

The module is intentionally unregistered until that review. No live data is used
by its tests. Tests use synthetic local PostgreSQL and private mocked storage.
