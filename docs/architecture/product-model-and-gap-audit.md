# Product Model and Gap Audit

**Reviewed:** 2026-10-13  
**Repository:** `eng540/Nashr`  
**Main HEAD observed:** `f0ea7a2c23f9f927e2f0f7cc8c9c9eba810b613c` (`fix: prevent Book Map 500 for discovery jobs (#128)`)  
**Scope:** code-backed architecture audit; not a claim of live product acceptance.

## Evidence inspected

- `app/domain/products.py`
- `app/application/control_plane.py`
- `app/domain/production_context.py`
- `app/application/production_jobs.py`
- `docs/architecture/current-baseline.md`
- `docs/architecture/target-architecture.md`
- `docs/architecture/system-map-and-change-policy.md`
- recent commits and PR #123/#127/#128 metadata.

This is a bounded audit of the product-to-context execution path. Database rows for the named video product, its previous job, provider records, and resulting artifact were not queried in this repository-only inspection. The live status of that job remains unverified.

## Current implementation (confirmed by code)

1. `ProductionProductDefinition` is a validated value object with `recipe_key`, `output_contract_key`, `policy_key`, `audience`, and `experience`. It does **not** currently declare identity or prompt references in this definition.
2. `ControlPlaneResolver.resolve_product(session, key)` resolves the active product and returns a `PinnedProduct` containing product ID, version ID, key, version number, and a serialized definition.
3. `ResolvedProductionContext` is an immutable, versioned snapshot (current schema version 6; supports schema versions 1–6). It has pinned types for prompt, identity, recipe, policy, output contract, and product. This establishes that the snapshot can represent multiple versioned components; it does not alone prove every product version selects all of them explicitly.
4. `ProductionJobRunner` reads a persisted `resolved_context` and validates that its pinned prompt key/version/body agrees with legacy prompt pin fields. For legacy jobs without a context snapshot it uses the already-persisted prompt body and refuses to guess a missing prompt. The compatibility recipe for pre-snapshot jobs is `BOOK_TO_TELEGRAM_POST`.
5. When a resolved context is present, the runner uses the pinned recipe if supplied, composes the pinned identity into the editorial prompt, and appends product audience and experience to that prompt. This proves these fields affect the prompt path for this runner. It does not prove the video capability consumes duration or every modality honors experience identically.
6. Job execution passes the pinned context payload to `ProductionExecutionContext`. This is the basis for resumability; the exact consistency of all creation paths and all modality adapters still requires a focused code/test audit.
7. The product definition stores component **keys**, while the resolved context types store concrete version IDs and snapshots. A key is not a version pin. The resolver's active-version lookup must therefore be completed before execution and persisted to avoid silent drift.

## Gap classification

| Requirement | Observed status | Evidence / limit | Required acceptance |
|---|---|---|---|
| Versioned product entity and active version resolution | Implemented in part | Resolver returns product ID/version ID and definition; inspect repositories/migrations during implementation | Test publish immutability and exact version resolution |
| Product definition declares recipe, policy, output contract, audience, experience | Implemented | `app/domain/products.py` | Preserve validation and test compatibility |
| Product explicitly declares prompt and identity versions/references | Gap in product definition | These are pinned separately in context; not fields in `ProductionProductDefinition` | Decide whether product version should select them explicitly; prevent silent defaults |
| Context pins prompt/identity/recipe/policy/output contract/product | Representable and partially integrated | `production_context.py`, `production_jobs.py` | Trace all creation, resume, retry, and legacy paths |
| No silent generic prompt fallback | Partially protected | Runner rejects jobs lacking an existing pinned prompt; prompt resolution at job creation still needs full path verification | API/service tests for missing/invalid product prompt configuration |
| Product derivation / parent lineage / component diff | Not proven in inspected code | UI supports versioned product management per PR #123, but no evidence here establishes derivation semantics | Implement only after checking all product APIs/models and adding lineage tests |
| Component compatibility preflight | Partially present | PR #124 made server validation authoritative; scope of checks must be verified against runtime capability constraints | Test product/recipe/output contract/provider compatibility before run |
| Experience reaches provider behavior | Partially implemented | Audience and experience appended to editorial prompt in runner; modality-specific execution not verified | Per-capability tests, not a generic assertion |
| Video duration consistency | Unresolved | Prior observed 5-second recipe setting conflicts with intended experience; provider capability/current product row not inspected here | Read product/version/recipe/provider limits, pass supported duration, inspect actual output metadata |
| `QUL_WA_LA_TAQUL_VIDEO` previous job and artifact | Unverified | No production DB/API query performed in this audit | Read-only production inspection before any new run |
| UI split: control vs factory | Implemented in part | PR #123 integrated product control UI; PR #127 reorganized factory; main commit #128 includes follow-up | Browser acceptance and current deployed-commit check remain separate |

## Recommended target (decision proposal, not yet an implementation claim)

- A published product version should resolve to a complete, validated runtime manifest: explicit product version, prompt version, identity version where required, recipe version, policy version, output-contract version, and required capability configuration.
- Reuse should reference immutable published component versions. Editing a draft or publishing a newer component version must not mutate a prior product version's meaning.
- Product derivation should create an independent product/version and record parent product/version plus an explicit changed/reused component manifest. Do not clone component rows unless there is a reason to fork that component.
- Legacy jobs should continue using their persisted context or existing prompt pin. Do not reconstruct old jobs from today's active versions.
- Validate output contract against recipe/capability before job creation; validate provider-specific settings again at the adapter boundary.
- Keep management in `/control`, execution in `/posts/workspace`, library in `/console`, and scheduling/distribution in `/publishing`.

These recommendations require implementation review against the complete models, migrations, repositories, API routes, and tests before any schema change. No migration is authorized by this audit alone.

## Next evidence-gathering sequence

1. Read product/identity/prompt/recipe/policy/output-contract models, repositories, migrations, service/API validation, and all product E2E tests on current main.
2. Query read-only production state for the exact video product version, active prompt/identity/recipe/policy/contract versions, prior job, item/provider operation, and Artifact/storage metadata.
3. Map duration from product UX through recipe/configuration to provider request and returned media metadata.
4. Build a per-modality matrix of pinning, provider parameters, Artifact validation, storage readback, and review visibility.
5. Only then open a narrowly scoped code PR for proven defects. No Telegram send and no full-book generation.
