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


## Output Contract Control Plane — current change

This change adds versioned output-contract data for Artifact kind, MIME type, content mode, required metadata fields, and inline-content limits. It seeds `TELEGRAM_POST v1` as the data description of the existing Post output and validates contract definitions independently of providers.

The runtime integration resolves `TELEGRAM_POST` at ProductionJob creation and pins the contract/version/definition in resolved-context schema v4. Artifact persistence validates kind, inline content, maximum length, and required metadata before saving, and records the contract key/version and MIME type on the Artifact. Schema-v1/v2/v3 contexts remain readable for historical jobs; they are not retroactively assigned a contract.

IMAGE and VIDEO contract definitions do not by themselves create image/video generation capabilities.


## Output Contract Runtime Integration — implementation change

New ProductionJobs resolve and pin the published `TELEGRAM_POST` contract in context schema v4. Post Artifact persistence validates the generated result against that immutable snapshot and persists contract key/version and MIME type as provenance. Existing context schemas v1–v3 remain compatible and are not backfilled with invented contract history. This integration applies to the existing Post capability only; it does not claim that IMAGE/VIDEO generation capabilities exist.


## Policy Control Plane — implementation change

A separate, versioned Production Policy Control Plane is implemented independently of Editorial Identity, Prompt Templates, Recipes, and Output Contracts. Policy definitions are declarative and restricted to validated fields; they cannot contain executable Python, SQL, provider configuration, or secrets. This slice establishes persistence, lifecycle APIs, and schema validation. Runtime pinning and enforcement remain a separate acceptance gate; this API alone does not claim that production output is policy-validated.


## Policy Runtime Integration — implementation change

New production jobs resolve and pin the published `EDITORIAL_DEFAULT` policy in resolved-context schema v5. A compatibility-default policy is seeded by migration to preserve the current behavior while making policy enforcement explicit. Artifact persistence validates generated Post content against that immutable snapshot (length bounds, required/forbidden terms, and URL allowance). Historical context schemas v1–v4 remain readable and are not assigned a policy retroactively.


## Policy Runtime Acceptance Gate

The follow-up acceptance tests now verify both sides of the runtime boundary: Artifact persistence rejects content that violates the pinned policy, and publishing a new policy version changes only newly created jobs. The original job retains its prior policy snapshot through publication of a replacement version.


## Recipe Engine Stage Configuration and Second Recipe

The Recipe Engine now passes each declarative stage's bounded configuration to its registered capability. The first supported configuration is `produce_post.style_instructions`, validated as plain text and never executable code. A second published recipe, `BOOK_TO_TELEGRAM_POST_BRIEF`, exercises this shared capability with concise-writing instructions. The Content Factory exposes the active recipe selector; both recipes still produce the existing Post artifact and retain the same review/publication path.
