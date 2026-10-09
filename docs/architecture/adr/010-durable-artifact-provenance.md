# ADR-010: Durable Generic Artifact and Provenance

- **Status:** Accepted for implementation
- **Date:** 2026-10-09
- **Scope:** Production Platform Foundation — Package E
- **Baseline:** main after PR #74

## Decision

Make Artifact a durable, provider-neutral output record without transferring ownership of existing editorial content from Post.

The artifacts table records artifact identity, kind, generic lifecycle status, source knowledge unit, optional production job, resolved context, output-contract reference, metadata, and either a backing Post reference or a direct content/storage reference. Supported kinds begin with POST, TEXT, IMAGE, VIDEO, and AUDIO. This establishes the data contract; it does not claim image/video generation or object storage is already implemented.

## Ownership

- Post remains the canonical store for current post text and editorial status (DRAFT/APPROVED/REJECTED).
- A POST Artifact points to its backing Post; the artifact table does not duplicate mutable post text or editorial status.
- Artifact.status is the generic output-record lifecycle (AVAILABLE/FAILED/ARCHIVED), distinct from Post editorial status.
- Non-Post artifacts can carry direct text content or a storage URI and MIME type.
- Output-contract key/version are nullable until the Output Contract Control Plane is implemented. No contract version is invented.
- ProductionJobItem.artifact_id links a run item to its output. The legacy post_id remains for existing Post-centric consumers.
- Artifact.production_job_id and its resolved-context snapshot preserve run-level provenance. Item links are queryable from ProductionJobItem.artifact_id.

## Migration and provenance

The migration creates an Artifact row for every existing Post using the Post UUID as the compatibility Artifact UUID. It links the backing Post and source KnowledgeUnit. It copies production_job_id and resolved_context only if exactly one historical ProductionJobItem references that Post. If multiple jobs reference the same Post, the migration leaves run-level provenance unknown instead of guessing. Existing job items are linked to their Post-backed Artifact through artifact_id.

For new output, the production capability persists the Artifact reference after the existing Post producer succeeds. Existing Artifact rows are not rewritten when a later job reuses a Post; that avoids attributing old content to a new run. A failed attempt to persist an Artifact can be retried, and the existing Post-backed Artifact identity is idempotent.

## Compatibility

- Keep Post review/approval, scheduling, publication, and Telegram behavior unchanged.
- Keep production_job_items.post_id and all existing Post APIs during the transition.
- Add artifact_id rather than replacing the old post_id.
- No new queue, worker, provider, or object-storage dependency.
- No claim that non-Post generation is operational; only the generic contract and persistence are prepared.

## Acceptance criteria

- Every existing Post has a durable POST Artifact after migration.
- New Post output is represented by a durable Artifact and linked from its production item.
- Reusing a Post does not overwrite its earlier provenance.
- Generic Artifact lifecycle state is separate from editorial status.
- IMAGE and VIDEO contracts can use storage references without Post-specific fields.
- Artifact detail API exposes output, source KnowledgeUnit, linked run items, run context, and optional output-contract metadata.
- Migration, unit, integration, frontend, build, and Browser E2E checks pass.
