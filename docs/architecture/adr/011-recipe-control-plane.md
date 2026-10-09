# ADR-011: Recipe Control Plane and Exact-Version Resolution

- **Status:** Accepted for implementation
- **Date:** 2026-10-09
- **Scope:** Production Platform Foundation — Recipe Control Plane
- **Supersedes:** The code-backed recipe catalog assumption in ADR-009; the capability execution boundary remains unchanged.

## Decision

Recipe definitions are persisted Control Plane data, not Python constants. The Control Plane stores a stable recipe identity and immutable version rows. Each version contains an ordered declarative stage list. The runtime resolves exactly one PUBLISHED version when a new ProductionJob is created and copies its identity, version, and stages into that job's ResolvedProductionContext.

The first published recipe is seeded by migration: BOOK_TO_TELEGRAM_POST v1 with the produce_post v1 capability. The domain constant remains only as a compatibility fallback for historical jobs created before recipe pinning; new jobs resolve the database-published recipe.

## Lifecycle

- New recipe identities start with version 1 in DRAFT.
- Only DRAFT versions can be edited or published.
- Publishing a DRAFT version archives the previous PUBLISHED version in the same transaction.
- A partial unique database index enforces at most one PUBLISHED version per recipe.
- The active PUBLISHED version cannot be archived directly; publish a replacement first.
- ARCHIVED versions cannot be edited or republished.
- Version numbers are monotonically allocated per recipe and are never reused.

## Capability safety

Recipe definitions are data, not executable code. Each stage names a capability key and version. The Control Plane rejects capability versions that are not registered by the current application. The engine executes only registered capabilities and fails explicitly if a pinned capability is unavailable. Adding a new recipe does not require a new orchestration branch; adding a new capability still requires a deliberate implementation and registration.

## Snapshot and compatibility

New ProductionJobs pin recipe ID, version-row ID, key, version, and ordered stage definitions in context schema v2. Publishing a new version affects only jobs created afterward. The runner consumes the stored snapshot and does not resolve the current PUBLISHED recipe on retry or recovery.

Schema-v2 snapshots written before this Control Plane was introduced may lack recipe database IDs; the parser continues to read them as legacy v2 snapshots. New snapshots include both persistent IDs. Schema-v1 and pre-snapshot jobs keep the existing BOOK_TO_TELEGRAM_POST compatibility path.

This package exposes a Control Plane API for creating recipe identities, creating/editing DRAFT versions, publishing, archiving, and inspecting versions. It does not yet add an admin UI, nor does it claim Identity, Policy, or Output Contract version entities are implemented.

## Acceptance criteria

- Recipe definition and lifecycle are stored in PostgreSQL.
- Exactly one PUBLISHED version per recipe is enforced by the database.
- New production jobs pin the exact active recipe version and its persistent IDs.
- Publishing a new recipe version cannot mutate an existing job's context.
- Only registered capability keys/versions can be published or executed.
- The engine remains independent of recipe-specific orchestration branches.
- Existing v1/v2 contexts and the Post/Review/Publishing path remain compatible.
- Migration, lifecycle API tests, backend, frontend, build, and Browser E2E checks pass.
