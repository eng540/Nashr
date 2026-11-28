# Unregistered production CREATE fence candidate

This candidate adds a server-owned linkage from an exact Dispatch to its
Execution, Decision, Grant and isolated control, with DB foreign keys and an
immutable-link trigger. It refactors isolated acquire/finish/Stop into
transaction-scoped internals plus unchanged fresh-session wrappers. The original
synthetic behavior stays covered. The protocol now has one explicitly permitted
unregistered consumer; containment tests forbid runtime and route consumers.

`claim_create` obtains a per-dispatch advisory fence, locks and resolves the exact
authoritative rows, verifies private bytes and current authority through the
write-authority guard, then initializes a missing legacy control/link and inserts
the unique CREATE claim in ONE transaction. No caller supplies pins, lifetime,
generation, decision or control IDs. Pre-existing synthetic controls without a
production link cannot be promoted. Initial link/claim/commit failure rolls back
the control as well. Concurrent first claims produce one winner; another DB
connection cannot see a partial control/link/claim.

`stop_dispatch` is a server-resolved single linked dispatch Stop, not batch Stop.
It uses the same advisory fence and control, freezes one immutable receipt and
revokes decision/grant atomically. An ACTIVE claim remains in flight. Retries
return original receipt/event history. It cannot accept synthetic client scope.

`finish_create` binds real result persistence to exact token/worker/claim version
CAS in the same transaction as receipt acknowledgement. A known late container
after Stop remains known but BLOCKED; UNKNOWN remains reconciliation-only. An
unused owner acknowledgement cancels without provider write. No result permits
repeating CREATE. Exact worker result input is internal only, not a client API.

## Not implemented, not cleared

No runtime, route or provider consumer is added. No production behavior changes.
The existing individual runtime and revoke/media paths are NOT yet using this
fence, so this cannot be activated beside them. Legacy first-claim atomicity is
proven for this new command only, not for every old worker until it is replaced.
The job stays DRAFT while this unregistered CREATE claim is ACTIVE; the future
runtime adapter must use this command exclusively and own the provider call.

PUBLISH always refuses. Thus its no-claim test proves refusal only, not repeated
IN_PROGRESS continuation acceptance. Status-only READ claims, persisted backoff,
media-ready evidence tied to control version, separate PUBLISH POST claim,
read-only result reconciliation and the real media-resume bridge remain open.
Batch membership/Stop remaining, exact authenticated activation and real Stop UI
also remain open. Recovery is unavailable. This candidate does not authorize any
posting, media exposure or activation and must be independently reviewed.
