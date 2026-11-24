# Private Instagram timing review

A review draft can carry a proposed local time and timezone. This does not create a runnable schedule or publishing approval. Riyadh and UTC are offered in the interface. The API checks the UTC offset against the named zone for the proposed instant, rejects ambiguous naive input and rejects saving a past proposal. Changing the time requires a new preview hash.

Draft cancellation is local, non-destructive, owner-only and same-origin. It never undoes a provider operation. Old pre-timing snapshots retain their compatibility digest. History labels elapsed proposals without executing them.

The due-time journey is demonstrated only in tests/integration/instagram_plan_simulation.py with an in-memory fake provider. It is not imported by the app, has no route or scheduler and uses no network, credentials or real media URL. Success, lost creation response and lost publish response are tested, with no repeated claim on the same synthetic review. The existing execution core rechecks pinned private bytes before simulated provider edges.

Still blocked for real publishing: live account acceptance, explicit owner approval, bounded immutable provider media access, final format checks and production scheduler wiring. No public social test or new API cost is introduced.
