# Isolated Instagram control protocol experiment

This delta adds synthetic controls, per-step claims, exact-scope stop receipts and
worker acknowledgement components. Nothing imports or registers the application
module. No route, real child resolver, provider adapter, scheduler, approval,
provenance bridge, frontend Stop or activation is included. These controls have no
relationship to production dispatch rows. They cannot stop or publish real work.
They are not a full implementation of the accepted activation contract.

## Transition writers

- acquire: locks control, validates expected generation/version, pins, connection,
  current decision/grant lifetime; inserts ACTIVE WRITE or READ claim. CREATE and
  PUBLISH are separate forever-unique write steps. PUBLISH requires known CREATE.
- finish: only exact token hash + worker-instance ID + claim version owning ACTIVE
  may transition it. WRITE becomes COMPLETED (known result or definite rejection),
  STOPPED_WITHOUT_WRITE (owner promises unused), or UNKNOWN (no replay).
- revoke/stop_batch: increment the same control generation and version; revoke
  future permission. They never claim a provider write or close an ACTIVE write.
- READ finish: COMPLETED only at exact control generation/version, otherwise
  SUPERSEDED. A new WRITE insert bumps control version. A late read cannot replace
  newer state. READs do not change write outcomes or grant status.
- Recovery: always refuses. Authenticated operator identity, verified exact-worker
  supervisor termination attestation, owner authorization and audited UNKNOWN-only
  transition are absent prerequisites. A log line or boolean does not qualify.

An abandoned unused write is STOPPED_WITHOUT_WRITE, never removed or reusable.
Even a definite pre-write provider rejection requires a NEW exact operation and
new dispatch. Do not relax the forever-unique dispatch/step constraint for retry.

Tokens use secrets.token_urlsafe(32), unique token hashes in DB. Raw tokens must
never enter logs, result descriptions, receipt events or HTTP bodies. In this
isolated version the trusted synthetic worker retains its minted token and passes
it to acquire/finish. Future adapters must preserve that boundary and must not
allow clients to choose ownership secrets. There is no token recovery endpoint.

## Boundaries still missing, fail closed

Synthetic pins and expiry fields model gate inputs; they do NOT verify production
decision rows, source media bytes, selections, grant identity or account ownership.
A future server-owned resolver must lock and verify those exact authoritative
records at every step. No app caller exists, so no placeholder truth is used to
publish. Recovery is unavailable, not partially enabled.

stop_batch accepts synthetic controls and explicit expected scope. It validates
all controls before any write, locks in ID order, persists immutable request and
version-0 receipts atomically. Retry compares original scope and returns its event
history, never resolves a later remaining set. DB triggers prevent audit UPDATE
or DELETE. The owning claim's terminal CAS appends one version-1 event to every
matching in-flight stop receipt. No client append path exists. This model does
not yet cancel real private children or bind their true batch ownership.

The isolated single-control revoke helper has no durable Stop receipt and is not
an API. All future user-visible Stops must use the receipt transaction. Known
published and unknown claims retain their outcomes. In-flight means requested,
not guaranteed stopped. Stop cannot undo publication or recall read media bytes.

## Synthetic 22-case acceptance ledger

Numbers refer to stop contract v2. Tests never send provider requests.

1. Independent worker contention and DB active-write unique index: proven.
2. CREATE/PUBLISH ordering and active-write exclusion: proven.
3. Claim before/after revocation, control-first lock contention: proven.
4. Claim then Stop then owner unused acknowledgement: proven, no network adapter.
5. Known CREATE then revoke blocks PUBLISH: proven.
6. Same control generation used by isolated revoke and stop: proven; real media
   resume / individual runtime integration deliberately absent and not accepted.
7. Expiry, grant revocation, pins, connection checks at both steps: synthetic proof;
   production record binding remains an activation prerequisite.
8. Wrong owner, delayed/duplicate version, terminal claim CAS: proven.
9. Post-revocation READ allowed without permission restoration: proven synthetically.
10. UNKNOWN never allows step replay, READ never mutates write result: proven.
11. Unique READ, active WRITE rejection, late superseded read: proven.
12. Persisted Retry-After with bounded interval: proven.
13. Published/unknown/pending/in-flight mixed receipts: proven.
14. Same request after acknowledgement retains original scope: proven.
15. Missing/duplicate/stale synthetic control fails before mutation: proven;
    authoritative real-child ownership resolver deliberately absent.
16. Receipt insertion and final commit failures rollback controls and request: proven.
17. No stealing/replacement write after UNKNOWN: proven; no process supervisor exists.
18. Forged/missing evidence recovery always refused: proven.
19. Valid attestation recovery unavailable, always fail closed. No acceptance claim.
20. Concurrent duplicate owner finish appends one event: proven.
21. No module consumer, endpoint or real dispatch linkage: source-level proof.
22. No new UI, so no Stop visual acceptance claim. Existing accepted review UI
    unchanged. Real 390/1280 Stop acceptance remains mandatory before activation.

The full activation matrix is NOT satisfied by 22 tests. Independent review must
assess this isolated scope and keep the missing production/visual cases blocked.
