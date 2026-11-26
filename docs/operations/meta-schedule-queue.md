# Saved Meta schedules in the content queue

The read-only `/api/publishing-queue` projection includes unclaimed Meta schedules in `PLANNED`, alongside existing Telegram plans. A pending Meta schedule is not publication evidence or an execution-readiness grant.

- Instagram: Unified execution draft, matching dispatch and decision, pending dispatch, approved unexpired decision, and recorded owner-session/trusted-message provenance.
- Facebook Reels: approved unexpired decision with a saved due time and recorded provenance.
- Facebook text/photo: approved unexpired decision with a saved due time, runtime snapshot object and recorded provenance. Dormant attempts without that context are excluded.

`pending_operations` exposes only operation ID, platform and due time for the returned original. It never exposes snapshots, evidence references, tokens or media grants. Cards link to the exact existing operation. Times display in Asia/Riyadh, explicitly labelled.

Failures and unresolved outcomes retain priority over `PLANNED`. Existing publication evidence remains visible independently. Revocation, expiry, cancellation, claimed work and synthetic rows do not count as pending schedules. Runtime still owns all final account/content/media/consent validation. No scheduler, approval, provider, migration or permission behavior changes here.
