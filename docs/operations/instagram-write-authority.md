# Unregistered transaction-scoped due-write authority guard

`instagram_write_authority.validate_locked` locks authoritative Dispatch,
Execution, Decision, Artifact, Instagram copy, destination selection, Connection,
saved Review, Inspection and exact Grant rows inside an explicit caller-owned
transaction. It checks individual Unified provenance, exact approved decision
hash and evidence-reference shape, public audience and media-disclosure scope,
due time, bounded grant identity/expiry/hash, current original/copy/selection,
account binding and actual private bytes. Authority and clock are checked again
after private byte reads. CREATE and PUBLISH have distinct accepted input states;
unknown/active/finished states cannot be reused. PRIVATE_BATCH_UNIFIED is rejected.

The helper adds no consumer, HTTP route, worker, control, claim or permission.
It returns ORM rows only to an internal caller, not an API. It does not commit.
An evidence-reference string is checked against stored approval records, not
accepted as independent proof of owner consent. Existing individual runtime is
unchanged. This is not an activation gate and must not be called in a separate
read transaction and followed by an unguarded provider write.

## Open integration gates

The next claim command must acquire the shared production fence first and call
this guard inside the SAME transaction as durable claim insertion and production
state transition. It must recheck all authority again before PUBLISH. The helper
does not prove that a fence was acquired. No production fence linkage exists yet.
Per-step unique claims, CAS results, shared Stop/revoke/media-resume generation,
frozen immutable Stop receipts, status-only media waiting/backoff, read-only
reconciliation, authenticated batch approval and Stop UI remain separate work.
Batch authorization additionally needs exact current selection version from the
saved batch, complete ownership and fresh whole-batch authority. This individual
write guard deliberately does not turn private preparation into live decisions.
