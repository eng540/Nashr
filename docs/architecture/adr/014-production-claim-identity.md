# ADR 014 — Explicit Production Claim Identity

- Status: Proposed in PR #125 follow-up; do not treat as accepted until PR review and CI pass.
- Date: 2026-10-12

## Context

A source material is reusable knowledge, not a one-time production slot. The same material may produce multiple posts or artifacts across products, identities, recipes, and intentional repeat runs. Replaying an HTTP request after a timeout must not create another job, while a deliberate new claim must be able to produce another independent output even when all settings match.

Legacy posts and artifacts may not have trustworthy production-context provenance. Missing provenance must remain unknown rather than being inferred from current Control Plane settings.

## Identity model

- **Production claim:** one explicit request to produce a selected scope under a resolved product/recipe/identity/policy/output-contract context. Its durable identity is `ProductionJobModel.id`.
- **Request replay identity:** `idempotency_key` identifies the submitted request delivery, not its settings or its output signature. The stored `request_fingerprint` rejects reuse of the same key for a different request. A deliberate new claim gets a fresh key.
- **Task item:** one `ProductionJobItemModel` is the durable work item for one knowledge unit within one claim. It tracks attempts, status, and the resulting Post or Artifact reference.
- **Output identity:** each Post or Artifact has its own primary key and lifecycle. A Post follows review, approval, scheduling, and publication; a generic Artifact follows its own artifact/review lifecycle. Generic artifacts are not forced through the Post lifecycle.

## Database constraints

Keep the following constraints as intentional per-claim concurrency/retry guards:

- `uq_production_job_items_job_knowledge_unit`: one work item per source material within a single claim. A second intentional output run is a second claim/job, not a duplicate item inserted into a running claim.
- `uq_artifacts_job_source_kind`: at most one artifact of a given kind for a source material within one claim. A second intentional output of the same kind is allowed under a new claim because it has a different job ID.
- `uq_posts_job_knowledge_unit`: at most one canonical Post for a material within one claim, while different claims may create separate Posts for that same material.
- `uq_production_jobs_idempotency_key`: only one job can own a request key, including concurrent submissions.

These constraints must not be removed without introducing an equivalent durable claim/output slot identity and concurrency-safe conflict handling. If a future recipe must intentionally emit multiple artifacts of the same kind for the same material *within one claim*, the model must first gain a stable output-slot/stage identity; dropping the current uniqueness constraint alone is unsafe.

## Completion indicators

The production factory's `NEEDS` / `DONE` indicator is a line-level availability view, not a permanent property of a knowledge unit. It is scoped by the selected product and active product version, its active recipe version, and the selected identity/version. Posts with missing provenance and outputs from other lines do not satisfy that line's completion state. Previous outputs remain available in their respective banks.

Because the current UI does not select an existing claim by ID, a new deliberate repeat run is started as a new claim; it is not inferred from matching settings. The `ALL` view remains the route to intentionally repeat work already produced by the selected line.

## Retry and concurrency rules

- Same idempotency key + same request fingerprint: return the original job.
- Same idempotency key + different fingerprint: reject the request.
- Concurrent same-key submissions: database uniqueness elects one owner; the losing request reads and returns that job after rollback.
- New explicit claim: new idempotency key and new job, even if all other request fields match.
- Resume/retry: operate on the original job and its pending/failed items; completed item references and the pinned resolved context remain intact.
- Do not send to Telegram or execute paid generation as part of CI acceptance tests.

## Compatibility

The migration adds nullable claim/provenance fields and retains legacy rows. Rows without a production job or resolved context are not assigned fabricated historical provenance. The Post lifecycle remains independent per Post ID, and schedule items continue to reference the exact Post they schedule.
