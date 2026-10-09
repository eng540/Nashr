# Nashr Production Platform — Stage Status (2026-10-10)

This is an additive implementation record. It does not replace earlier baseline, target architecture, or roadmap documents.

## Verified baseline

- Recipe Control Plane baseline commit: `6f93a01b88ea3c3cb05c66d4cc7eec5fc2d00896`. Identity lifecycle implementation is recorded in PR #83.
- Recipe Control Plane is persisted and versioned in PostgreSQL.
- The CI run for that exact main commit passed migrations, backend tests, frontend typecheck, frontend unit tests, production build, and browser E2E.
- Duplicate PR #81 was closed because its change was already present on main; it was not merged.

## Identity Control Plane and runtime — current implementation

The identity lifecycle API persists structured purpose, audience, voice, tone, principles, objectives, and constraints with DRAFT / PUBLISHED / ARCHIVED versioning and a database-enforced single published version.

The runtime integration resolves an explicitly selected published identity at ProductionJob creation, pins its IDs/version/full definition in resolved-context schema v3, and composes the pinned identity into the model prompt. The Content Factory now exposes a selector for published identities. If no identity is selected, schema v2 and the existing prompt behavior remain unchanged.

Acceptance tests cover v3 snapshot round-tripping, required recipe+identity, and version immutability: publishing identity v2 must not alter an existing job's v1 snapshot or prompt. Schema-v1/v2 contexts and the existing Post → Review → Scheduling → Publication → Telegram path remain compatible.

This stage should only be called complete if the latest CI passes, including browser E2E.

## Remaining Control Plane layers

Policy and Output Contract are separate upcoming layers. They must not be folded into Identity or Prompt Template. Generic IMAGE and VIDEO Artifact kinds in the schema do not by themselves constitute working image/video production capabilities; each requires registered execution capability, provider adapter, persistence/provenance, validation, and tests.
