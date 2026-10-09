# Nashr Production Platform — Stage Status (2026-10-10)

This is an additive implementation record. It does not replace earlier baseline, target architecture, or roadmap documents.

## Verified baseline

- Main commit: `6f93a01b88ea3c3cb05c66d4cc7eec5fc2d00896`.
- Recipe Control Plane is persisted and versioned in PostgreSQL.
- The CI run for that exact main commit passed migrations, backend tests, frontend typecheck, frontend unit tests, production build, and browser E2E.
- Duplicate PR #81 was closed because its change was already present on main; it was not merged.

## Identity Control Plane — current change

This stage adds a persisted, versioned editorial identity definition with:
- stable identity key and descriptive metadata;
- structured purpose, audience, voice, tone, principles, objectives, and constraints;
- DRAFT / PUBLISHED / ARCHIVED lifecycle;
- immutable published versions and one active published version per identity;
- API lifecycle tests and a database migration.

Identity is kept distinct from recipe, prompt template, policy, and output contract.

## Explicit completion boundary

This change alone does **not** mean Identity has influenced generated content. Runtime integration is still required:
1. Resolve the selected identity when creating a ProductionJob.
2. Pin identity ID, version ID, and full validated definition in a new resolved-context schema version.
3. Make the existing production capability consume the pinned identity through a provider-neutral prompt/context composition boundary.
4. Prove that publishing a new identity version does not change an existing job's output context or retry behavior.
5. Preserve schema-v1/v2 contexts and the existing Post → Review → Scheduling → Publication → Telegram path.

Do not describe this foundation as complete until those runtime acceptance checks pass.

## Remaining Control Plane layers

Policy and Output Contract are separate upcoming layers. They must not be folded into Identity or Prompt Template. Generic IMAGE and VIDEO Artifact kinds in the schema do not by themselves constitute working image/video production capabilities; each requires registered execution capability, provider adapter, persistence/provenance, validation, and tests.
