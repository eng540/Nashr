# Dormant atomic private batch preparation

This internal module is deliberately unregistered. No HTTP route, UI button,
worker or approval path calls it. It inserts private review/job rows and one
preparation receipt only, never decisions, dispatches, grants or provider writes.
It does not read media bytes. A saved selected inspection is historical evidence,
not fresh media validation. The table has no runnable relationship.

One fresh transaction owns all exact ordered children. Stable request key binds
the exact private review ID/hash. Reusing it returns the immutable receipt,
including after later changes, not a fresh readiness/approval. Another key cannot
create a second preparation for the same review. Validation of all children
precedes first insertion. Any later failure rolls back receipt and every child.
Second connections cannot observe partially inserted rows before commit.

Source/copy/selection/account/inspection/existing-job rows are locked in stable
order with NOWAIT and lifecycle try-lock. Contention fails closed; no automatic
retry. Full saved private snapshot including exclusions and historical operation
conflicts must match and have no blockers. Each prepared child records exact
owned preparation/review/job IDs, original/copy/inspection/account bindings,
outgoing text, feed choice and time. Existing jobs are never silently adopted.

Prepared jobs use the distinct PRIVATE_BATCH_UNIFIED provenance marker, not the
existing UNIFIED marker. This is intentional defense in depth: individual
proposal/approval/stage/runtime validation and the dormant atomic coordinator
reject them. No internal function alone upgrades them. Returning their IDs is
not sufficient to enter an existing single-item approval route. They do block
other same-account implicit preparation as historical operations should.

This tranche does not implement conflict exclusions. Future exact activation
may exclude only the owned child IDs after validating receipt ownership, exact
review mapping, DRAFT/unclaimed state, bindings and no decision/dispatch. Never
ignore all DRAFT jobs or all children from a similar material/account. Source
private review currentness will naturally become stale after its own jobs are
inserted; do not mutate its historical snapshot or claim it is revalidated.

No cancel/stop endpoint is added. A future private child cancellation must be
atomic and preserve the immutable preparation receipt, and must never revive it
on key retry. Existing individual cancel rejects this unsupported provenance.
No one should describe these prepared rows as approved or ready to run.

Fresh account verification, pinned-byte checks, current conflict checks, strict
exact public/media consent, all-or-none decisions/dispatches, per-item results,
stop/revocation and uncertain-outcome recovery remain prerequisites to activating
the full batch workflow. Atomic database insertion is not atomic remote posting.
