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

This stage establishes the durable identity contract and lifecycle. It does **not** claim the production runner already consumes or pins identity versions. Runtime resolution and immutable identity snapshots in ProductionJob are the next required integration gate. Until that is implemented, an identity configured through this API does not alter production output.

## Consequences

- Multiple editorial purposes can be configured without changing the generic engine's orchestration code.
- A later runtime change must pin the exact identity version in the ProductionJob's resolved context so publishing a new version cannot change retries or existing jobs.
- Policy and Output Contract remain separate entities and are not implied by this identity model.
- Existing BOOK_TO_TELEGRAM_POST, Post review, scheduling, publication, and Telegram distribution remain unchanged.
