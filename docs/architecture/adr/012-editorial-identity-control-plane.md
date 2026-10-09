# ADR-012: Versioned Editorial Identity Control Plane

- **Status:** Accepted for implementation
- **Date:** 2026-10-10
- **Scope:** Production Platform Foundation — Editorial Identity
- **Depends on:** ADR-011 Recipe Control Plane

## Decision

Editorial Identity is persisted, versioned Control Plane data rather than a hard-coded Python persona or a prompt-only convention. An identity definition records its purpose, audience, voice, tone, principles, objectives, and constraints. It is deliberately separate from a production recipe, prompt template, policy, and output contract.

Each identity has a stable key and immutable published versions. New identities begin with a DRAFT v1; only DRAFT versions can be edited or published; publishing a replacement archives the previous published version. PostgreSQL enforces one published version per identity.

## API and data boundary

The first implementation exposes a Control Plane API for listing and inspecting identities, creating an identity, creating/editing DRAFT versions, publishing, and archiving. Definition data is validated as structured text/lists; it cannot contain executable Python, credentials, SQL, or provider-specific behavior.

## Runtime boundary

The runtime integration adds resolved-context schema v3. When a caller selects an identity, new ProductionJobs resolve the active PUBLISHED version once and snapshot identity ID, version-row ID, key, version, and the complete validated definition alongside the recipe and prompt. The Content Factory exposes the published identities and lets the operator select one for a production run.

The production runner composes only the identity snapshot stored on the job into the editorial prompt. It does not re-resolve the current identity during retries. Jobs created without an identity retain schema v2 and the existing prompt behavior; schema-v1/v2 historical snapshots remain readable.

Acceptance requires tests proving that publishing a replacement identity leaves an existing job's snapshot and effective prompt unchanged. This still does not mean Policy or Output Contract is implemented.

## Consequences

- Multiple editorial purposes can be configured and selected without adding identity-specific orchestration branches to the generic engine.
- Identity data is passed through a provider-neutral composition boundary; provider adapters remain outside the identity domain.
- Policy and Output Contract remain separate entities and are not implied by this identity model.
- Existing BOOK_TO_TELEGRAM_POST, Post review, scheduling, publication, and Telegram distribution remain unchanged.
