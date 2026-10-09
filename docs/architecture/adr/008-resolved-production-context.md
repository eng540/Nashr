# ADR-008: Resolved Production Context Snapshot

- **Status:** Accepted for implementation
- **Date:** 2026-10-09
- **Scope:** Production Platform Foundation — Package C
- **Baseline:** main after PR #72
- **Decision:** Persist and validate the exact configuration resolved for each production job.

## Context

PR #68 pinned the editorial prompt key, version, and body on ProductionJob. Package B exposed that information to the user, but the three independent columns are only the first step toward a stable, versioned production context. Future Identity, Policy, Recipe, and Output Contract versions must not be silently inferred from whichever version happens to be published when a job resumes.

## Decision

### 1. One versioned context document

ProductionJob.resolved_context is a nullable PostgreSQL JSONB document parsed by the domain contract in app.domain.production_context. Schema version 1 records the prompt template currently resolved by the implemented Control Plane:

- schema_version: context schema version.
- origin: RUNTIME_RESOLUTION for a new snapshot or LEGACY_PIN_BACKFILL when the migration can prove the historic key/version/body against a persisted template version.
- captured_at: UTC timestamp for runtime snapshots; null for legacy backfills because the exact historical resolution instant is not provable.
- prompt_template: template ID, version-row ID, key, version number, and exact body used.

The domain parser validates the schema version, origin, identifiers, key, positive version, and non-empty body. Unknown schema versions and malformed snapshots are rejected; the runner must not silently resolve the current published version as a fallback.

This version-1 document records only the configuration that exists and is consumed today. It does not claim that Identity, Policy, Recipe, or Output Contract version entities have already been implemented. When those consumers are implemented, a deliberate context-schema revision must add their explicit IDs/versions and resolved payloads.

### 2. Capture once; never resolve again for the same job

A new job resolves the published prompt once and stores the context in the same transaction as the job and its items. Retry, resume, and stale-job recovery consume the persisted context. Publishing a newer prompt version affects newly created jobs only.

The existing prompt columns remain temporarily as compatibility fields for current API consumers and old jobs. When a context snapshot exists, the runner validates that its prompt key/version/body agree with those fields and uses the snapshot as the execution source of truth. A conflict or invalid snapshot fails explicitly rather than switching prompts.

### 3. Safe treatment of historical jobs

The migration backfills a context only when the old job's prompt key, version, and body match an exact row in the existing Control Plane. It records LEGACY_PIN_BACKFILL and leaves captured_at null. If the match cannot be proven, the context stays null; existing pinned columns remain usable by the compatibility path, and jobs with no complete pin continue to fail explicitly. No historical version is guessed.

### 4. Compatibility and scope

- Keep BOOK_TO_TELEGRAM_POST behavior, Post review, scheduling, publication, and workspace ownership unchanged.
- No Identity/Policy/Recipe/Output Contract tables are introduced by this package.
- No new queue, worker, service, or provider coupling is introduced.
- JSONB is nullable so rollout is safe for existing records; backfill is evidence-based.
- The legacy columns are not removed in this package. Their removal requires a separate compatibility decision after all consumers use the context contract.

## Acceptance criteria

- Runtime context includes stable template and version-row IDs as well as key, version, and body.
- Snapshot creation and job creation are atomic.
- A later published prompt cannot mutate an existing job context or alter its retry prompt.
- Legacy jobs with a complete existing pin remain runnable without resolving the current published version.
- Malformed or conflicting snapshots fail explicitly.
- Migration backfills only provable legacy context and never invents a capture timestamp.
- Unit, integration, migration, and full CI checks pass.
