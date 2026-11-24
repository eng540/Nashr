# Unified approved-content operations queue

The read-only `/api/publishing-queue` projection combines approved Post records and
approved available generic Artifact originals. It excludes POST wrapper artifacts
and derived PLATFORM_VARIANT records. No migrations or execution contracts change.

Search, origin/state/kind filters, deterministic ordering and bounded pagination run
in SQL. Related copies, distribution choices and plans are loaded in batches for
only the returned page. No media download, preparation, draft, schedule or send is
triggered by reading it.

States are observations, not permission:
- ATTENTION: a failed publication or non-cancelled failed schedule item exists.
- PLANNED: a draft/active/paused plan still has a pending/processing/failed item.
- PUBLISHED: a publication is marked published and has a non-empty external id or
  external-id list. This is historical evidence, not a promise the remote post
  remains visible forever.
- APPROVED: none of those facts is recorded. This does not assert eligibility.

Failure takes display priority over a plan and historical publication, so later
problems are not hidden. A cancelled plan does not mean published. Multiple states
can exist across history; the original record and latest-plan links expose details.
Central-copy counts and validated fields never imply media/account/execution readiness.
Execution-ready is deliberately false in this projection. Existing scheduling
routes remain responsible for their own checks. Post and Artifact selection are
not silently combined into a legacy schedule request.

Verification: 586 backend tests passed, 1 skipped; 45 browser cases passed across
bounded runs using a dedicated database where needed; production build passed.
Desktop and390px mobile queue pixels inspected. No production writes needed.
