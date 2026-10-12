# ADR 014 — Production Claim and Execution Identity

- Decision: retain the unified `ProductionJobModel` aggregate for this implementation; the merge gate remains open until the PR's latest CI is green and reviewed.
- Date: 2026-10-12
- Scope: PR #125

## Context

A source material is reusable knowledge, not a one-time production slot. The same material may produce multiple outputs across products, identities, recipes, and intentional repeat runs. Replaying an HTTP request after a timeout must not create duplicate work, while a deliberate new claim must be able to create independent output even when every production setting matches a prior claim.

Legacy posts and artifacts may not have trustworthy production-context provenance. Missing provenance remains unknown rather than being inferred from current Control Plane settings.

## Decision: one durable claim/execution aggregate, not a separate Claim table

In the current lifecycle, a production request creates one durable `ProductionJobModel` row, and that row represents both (a) the user's production claim and (b) the long-lived execution aggregate that processes it. This is a deliberate unified model, not a claim that the two concepts are identical in every possible future architecture.

A separate `ProductionClaimModel` would currently be a wrapper around one job: the system has no independent claim lifecycle, no supported operation that creates a second job execution for one claim, and no separate execution-history records. Adding a claim table now would introduce a foreign key, backfill, consistency rules, and another object to resolve without enabling a current workflow that the job aggregate cannot express. The choice is therefore to avoid a shape-only layer and make the boundary/limitations explicit.

The model's identifiers have these meanings:

- **Claim and execution aggregate identity:** `ProductionJobModel.id`. It is durable and identifies the work aggregate created for one explicit claim. It is not a settings hash and is never reused for a later intentional claim.
- **HTTP request replay identity:** `idempotency_key` identifies a delivery of a request. `request_fingerprint` binds that key to the canonical request payload. The same key and fingerprint return the same job; the same key with a different fingerprint is rejected. A new explicit claim uses a fresh key, even if the payload is otherwise identical.
- **Per-material execution state:** `ProductionJobItemModel.id` identifies a durable work item within the aggregate. It tracks attempts, provider operation/reconciliation state, and references to completed outputs. Resume/retry updates this existing item/job; it does not create a new claim or discard completed output references.
- **Output identity:** every Post and Artifact has its own primary key and lifecycle. Posts have independent review/approval/rejection and exact schedule/publication references; generic Artifacts are not forced through the Post lifecycle.

## Explicit limits of the unified model

This design does **not** currently support:

1. One claim owning multiple separately identified `ProductionJobModel` executions or an append-only history of execution generations.
2. Independently restarting/fanning out one material into several same-kind output slots within the same claim.
3. A separate business-claim lifecycle (cancel/expire/authorize a claim independently of its execution aggregate).

Retry/resume is intentionally an operation on the original job and its existing items. A deliberate rerun—even with identical settings—is a new claim and a new job. If requirements later demand any of the three cases above, introduce a first-class claim entity with one-to-many execution records and migrate the replay key/fingerprint to the claim; do not simulate that separation by renaming fields or by deleting uniqueness constraints.

## Database constraints

Keep these constraints as intentional per-claim concurrency/retry guards:

- `uq_production_jobs_idempotency_key`: one durable job owns a request replay key.
- `uq_production_job_items_job_knowledge_unit`: one work item per source material within one claim/job.
- `uq_artifacts_job_source_kind`: at most one Artifact of a given kind for a source material within one claim/job.
- `uq_posts_job_knowledge_unit`: at most one canonical Post for a material within one claim/job; different jobs can produce independent Posts for that material.

A second intentional output of the same kind is supported in a new explicit claim/job. Multiple same-kind outputs for the same material *inside one claim* require a stable output-slot/stage identity and safe conflict handling first; dropping uniqueness alone is unsafe.

## NEEDS / DONE semantics

The current Post Bank completion count is specifically a **Post-completion indicator**. It counts Posts only when their owning job has a persisted, matching resolved product/version, recipe/version, and identity/version context. It does not treat an Artifact as a completed text Post, and it does not infer a line from a legacy Post without reliable provenance. This prevents cross-product and cross-identity contamination.

This indicator is not a universal completion metric for every artifact kind. An image/audio/video product must use an artifact-kind/output-contract-aware indicator before its UI can claim that those non-Post outputs are complete. Do not reuse the Post count as a generic multi-output completion count. Previous outputs remain available in their respective banks.

Because the current UI does not select an existing claim by ID, a deliberate repeat run is started explicitly as a new claim; it is never inferred from matching settings. The `ALL` view is the route to intentionally repeat work already produced by the selected line.

## Retry and concurrency rules

- Same idempotency key + same request fingerprint: return the original job.
- Same idempotency key + different fingerprint: reject the request.
- Concurrent same-key submissions: the unique constraint elects one owner; the losing request resolves to that same job after the conflict is handled.
- New explicit claim: fresh idempotency key and new job, even if all production settings match.
- Resume/retry: operate on the original job and its pending/failed items; completed item/output references and the pinned resolved context remain intact.
- CI acceptance must not send to Telegram, perform paid generation, or touch Railway.

## Historical-data compatibility

The migration adds nullable replay/provenance fields and retains legacy rows. Rows without a production job or a persisted resolved context are not assigned fabricated historical provenance. Post review and schedule/publication references remain attached to the exact Post ID.
