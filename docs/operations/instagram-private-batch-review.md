# Private exact Instagram batch reviews

This first workflow tranche saves a private review of one to twenty exact ordered
approved IMAGE/VIDEO originals. It is not a schedule or outgoing consent. The
atomic execution coordinator remains unregistered and untouched. The new table
has no dispatch, decision, grant or worker relationship. No approve endpoint is
provided. Deployment alone never saves a review or changes existing content.

The owner supplies every original ID, Reel feed choice, future time within seven
days and IANA zone. Preview reads saved original/copy/selection/account/inspection
and existing operation history. It does not verify Meta, read bytes, create media
URLs, prepare copies or silently repair selections. Instagram exclusions, stale
choices, missing account/inspection and previous same-account operations remain
visible blockers. A blocked private review may be saved for later work, but cannot
be activated. Another account's result does not prove delivery to this account.

Saving rechecks the complete snapshot under source/copy/selection/account locks,
uses a private review serialization lock, and commits one immutable review row.
The key binds exact ordered inputs and preview hash; retry returns the same row,
including after cancellation, never a revived review. The stored connection
binding digest detects reconnect/config/token changes without returning secrets.
The snapshot is a historical observation, not a claim that provider/account/media
facts remain current. Job or inspection changes after the final read can make a
saved review stale immediately. Any future activation must independently lock,
revalidate and pin its complete execution inputs and review current history.

History returns the latest twenty reviews, without fan-out currentness checks.
An explicit read of one exact saved review returns its current stale indication. Each
item includes its latest thirty saved execution records and an explicit total /
truncation flag. Conflict checks count all noncancelled same-account operations,
not only displayed history, including failed/uncertain/published operations.
Local cancellation affects this review only, never existing individual jobs or
remote content. There is no bulk cancellation of already running publications.

Owner authentication, same-origin POSTs, strict fields and no-store responses
apply to preview/save/history/cancel. Inputs cannot supply authority flags.
All tests use synthetic local state and mocked browser data. No production
review save, schedule, provider call, account check or publication is needed.

## Remaining before usable batch execution

- Private atomic preparation of exact reviewed inputs without individual staging.
- Fresh account/media/history checks, pinned bytes and stale/concurrency gates.
- Separate explicit exact-batch public-audience/media-disclosure approval.
- Per-item dispatch results, stop/revocation and uncertain-outcome recovery.
- Independent acceptance of that whole activation boundary before registration.

Atomic database approval is not atomic remote publication. Earlier items may be
accepted while later items fail. No implicit retry/repost or account fallback.
Facebook adapters and all other platforms remain separate work.
