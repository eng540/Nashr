# Central content approval and distribution selection

GET /api/artifacts/{id}/distribution-readiness evaluates the approved original without providers, silent trimming or writes. A central approval is inherited, not repeated. ORIGINAL_ELIGIBLE is preliminary copy eligibility, not proof that media, destination, account permissions or execution have passed. Unsupported or unverified requirements have explicit blockers. Existing generated variants remain intact and are not silently upgraded or overwritten.

POST /api/artifacts/distribution-selection atomically saves explicit platform inclusion or exclusion for up to100 approved originals. An empty platform list clears intent. All IDs and current source fingerprints are required. A stale source rejects the whole batch. No drafts, schedules or external requests result. The selection is stored outside artifact metadata so existing album and LivePhoto fingerprints, original content, approvals and update timestamps remain unchanged.

The bank offers individual and batch controls, selectall/clearall and original preview. Saving a batch replaces only those materials' choices; individual exceptions can then be saved separately. Existing publication and schedule authorization remains unchanged. Distribution intent does not authorize execution, cancel old schedules or connect unsupported platforms. Account, byte-level media and platform-specific final validation still belong to the publishing path.

AI-independent fallback is the unchanged original only when its copy checks pass. This increment does not claim automatic semantic adaptation, SEO generation, media transcoding, provider health or new social connectors. Those remain explicit work, not simulated readiness.
