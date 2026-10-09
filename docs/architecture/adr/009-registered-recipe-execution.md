# ADR-009: Registered Recipe Execution Boundary

- **Status:** Accepted for implementation
- **Date:** 2026-10-09
- **Scope:** Production Platform Foundation — Package D
- **Baseline:** main after PR #73

## Decision

Introduce a provider-neutral recipe contract and a bounded execution engine. The engine consumes a pinned, ordered list of stages; each stage names a registered capability key and version. It does not contain product-specific if/else branches, provider SDK details, Post persistence logic, or Telegram delivery behavior.

The first recipe is BOOK_TO_TELEGRAM_POST v1. It contains one stage, produce-post, which invokes the existing Post production application through the produce_post v1 capability. That capability adapts the current Post result to the provider-neutral Artifact contract. Review, approval, scheduling, publication, and Telegram remain outside the engine.

## Recipe and capability rules

- Recipe definitions are immutable, declarative data with a key, version, and non-empty ordered stage list.
- Stage keys are unique within a recipe.
- A stage can invoke only a registered capability key/version; configuration is not executable code.
- The engine rejects a pinned recipe definition that differs from the registered definition for the same key/version.
- A recipe version is immutable: a behavior change requires a new version key, not mutation of an existing version.
- The last stage must return a validated Artifact. Intermediate stage values are passed to the next capability in memory; durable item-level progress and retry remain owned by ProductionJob.
- Current retries rerun an item's recipe from the beginning. Stage-level durable checkpoints are not claimed by this package.

## Snapshot and compatibility

New jobs use context schema v2, pinning the recipe key/version and ordered stage/capability versions beside the prompt snapshot. Existing schema-v1 and pre-snapshot jobs retain the only path that existed before this package, BOOK_TO_TELEGRAM_POST v1. They are not rewritten to claim a recipe snapshot they never stored.

The initial catalog contains one explicitly registered recipe. The RecipeRegistry and CapabilityRegistry are narrow boundaries, so recipe definitions and capabilities can be supplied by a validated Control Plane catalog without changing engine orchestration. This package does not yet claim that recipe authoring is exposed through an admin UI, nor that Identity, Policy, or Output Contract versioning is implemented.

## Acceptance criteria

- BOOK_TO_TELEGRAM_POST runs through the generic engine and a registered capability.
- The runner no longer invokes ProducePost or converts Post to Artifact directly; that knowledge belongs to the capability adapter.
- A pinned recipe cannot silently drift under the same version.
- Unknown recipes/capabilities and invalid final outputs fail explicitly.
- Existing per-item progress, failure isolation, retry, resume, and recovery behavior remains intact.
- Context schema v1 remains readable; new jobs capture schema v2.
- Unit, integration, migration, TypeScript, build, and Browser E2E checks pass.
