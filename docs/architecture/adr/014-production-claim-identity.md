# ADR 014 — Separate Production Claim and Execution Identity

- Decision: implement a first-class `ProductionClaimModel` and a distinct `ProductionJobModel` execution record.
- Status: Implemented in PR #125; merge gate remains open until CI on the final commit succeeds and the changes are reviewed.
- Date: 2026-10-12

## Context

A production request is durable user intent. Its HTTP delivery may be repeated after a timeout, and a deliberate new request may have exactly the same settings while still requiring independent output. The request identity must therefore not be the execution identity, nor a hash of production settings.

Legacy jobs, posts, and artifacts may lack trustworthy claim or production-context provenance. Missing provenance remains unknown rather than being inferred.

## Decision and responsibilities

### ProductionClaimModel — durable request/claim identity

Each explicit production request creates a row in `production_claims` with its own UUID. It stores source and scope, the optional HTTP `idempotency_key`, the canonical `request_fingerprint`, request payload when available, and creation time.

- `ProductionClaimModel.id` is the permanent claim identity.
- `idempotency_key` and `request_fingerprint` live on the claim, not on the execution.
- The unique key constraint ensures at most one claim owns an idempotency key.
- Same key and same fingerprint resolve to the same claim and its linked job.
- Same key and a different fingerprint are rejected.
- A new explicit request uses a fresh key (or no key) and creates a new claim even when settings match.

### ProductionJobModel — execution identity and state

Each newly created claim currently has one execution job. `ProductionJobModel.id` is an independent UUID and `ProductionJobModel.claim_id` is a unique nullable foreign key to the claim. The unique relationship expresses the current one-job-per-claim cardinality without claiming that job ID is the claim ID.

The job owns execution status, attempts, timestamps, pinned prompt/context, and item collection. Resume/retry operates on this same job and its existing items. Completed item/output references and pinned context are preserved; existing reconciliation guards still block unsafe regeneration when a provider outcome is unknown.

A one-to-one relationship is sufficient for the current scope. Multiple execution generations per claim are not introduced. If that requirement appears, the relationship can deliberately become one-to-many with explicit generation semantics.

## Database and historical compatibility

Migration `0042_separate_production_claim.py` creates the claims table and adds nullable `production_jobs.claim_id`.

- Existing jobs are assigned a claim only when both an idempotency key and request fingerprint were already persisted; the migration creates a new claim UUID independent of the job UUID.
- Legacy jobs without that evidence remain intact with `claim_id = NULL`. No historical claim, request payload, or provenance is fabricated for them.
- Read/status and resume paths continue to address the original job ID and do not require a claim ID, so legacy jobs remain readable and recoverable.
- The unique nullable `claim_id` constraint permits legacy nulls while preventing two execution jobs from being attached to one claim.
- Post, schedule, publication, artifact, and production-item identities and foreign-key relationships remain intact.

The migration downgrade restores replay fields from persisted claims where possible. It does not delete or merge posts or execution items.

## Output and completion semantics

Posts and Artifacts retain independent IDs and lifecycles. Review, approval, rejection, schedules, and publications continue to reference the exact Post ID. Existing per-job constraints remain:

- `uq_production_job_items_job_knowledge_unit`: one work item per source material per execution.
- `uq_artifacts_job_source_kind`: at most one Artifact of a kind per material per execution.
- `uq_posts_job_knowledge_unit`: at most one canonical Post per material per execution.

Independent claims/jobs can create independent outputs of the same kind. Multiple same-kind output slots for the same material inside one claim/job are **not** supported until a stable output-slot/stage identity, safe uniqueness constraint, and corresponding tests are implemented. Dropping a constraint alone is not acceptable.

Post Bank `NEEDS / DONE` remains specifically a Post-completion indicator. It matches persisted, trustworthy product/version, recipe/version, and identity/version context; it does not infer a line for legacy Posts and does not count Audio/Image/Video Artifacts as completed text Posts. Other output types require an artifact-kind/output-contract-aware completion indicator.

## Acceptance rules

1. Same idempotency key + same fingerprint returns the same claim and job.
2. Same idempotency key + different fingerprint is rejected.
3. Concurrent same-key requests converge on one claim/job through database uniqueness and conflict recovery.
4. A new explicit claim with identical settings gets distinct claim and job UUIDs.
5. Resume/retry operates on the original job and preserves completed outputs and pinned context.
6. CI must cover migrations, backend, frontend typecheck/unit/build, and Playwright.
7. No Railway operations, paid generation, or Telegram sends are part of this acceptance gate.
