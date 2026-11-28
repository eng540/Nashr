# Unregistered media-wait claim bridge

An immutable status observation binds an exact owned READ claim to dispatch,
container and post-finish control version. Read claims use persisted backoff and
exact worker/token/version CAS. Late reads after a Stop are SUPERSEDED and create
no readiness observation. Read-only observations do not restore permission after
revocation/expiry. Connection provenance must still match; no account fallback.

Repeated IN_PROGRESS status reads never insert a unique PUBLISH claim. Only a
fresh FINISHED observation (at most60seconds, checked again after private byte
reads) at the unchanged control version can reach PUBLISH claim acquisition. That
command locks the same production fence and authoritative rows, rechecks decision,
grant, source/copy/selection/account/inspection and private bytes, then inserts a
forever-unique PUBLISH claim. Stop between status and claim blocks it. No GET or
POST is called by these helpers, so provider status cannot hide inside a mutation
claim. A future trusted worker must separately call status GET then the final
POST-only adapter under the acquired claim.

PUBLISH result CAS updates real job/dispatch and revokes grant atomically with
one acknowledgement per in-flight Stop. Known late media remains known even
after Stop, UNKNOWN is reconciliation-only, and no terminal outcome reuses the
PUBLISH step. Status input and media ID input are internal worker-only data, not
an authenticated public API and not independent authority.

## Remaining gates

No runtime/API consumer, batch activation, provider edge or Stop UI is added.
The old live individual worker/revoke/media delivery still bypass these new
commands and must be replaced cohesively before activation. The first CREATE
command requires an already valid grant; atomic first-grant initialization and
pre-claim revocation for legacy pending rows remain integration work. The
production fence cannot be enabled beside old helpers. Read result/permalink
reconciliation and supervisor recovery remain open. Batch membership and Stop
remaining must use complete server-owned membership, not client dispatch lists.

Tests use synthetic PostgreSQL/private mocked storage and no network provider.
