# Product Model and Gap Audit

**Reviewed:** 2026-10-13  
**Repository:** `eng540/Nashr`  
**Current main HEAD after PR #129:** `195bf73b0276203f125f7f8a2d45950cf7d9971e` (documentation merge).  
**Production code commit observed in Railway:** `f0ea7a2c23f9f927e2f0f7cc8c9c9eba810b613c` (deployment succeeded 2026-10-12).  
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


## Expanded execution-path evidence — 2026-10-13

### Create path and component resolution

- `create_production_job(...)` in `app/application/production_jobs.py` resolves `EDITORIAL_PROMPT_KEY = editorial.drafter` before resolving the product. The product definition has no prompt reference, so all new jobs using this path receive the active editorial.drafter version, regardless of product.
- Recipe, policy, and output-contract are selected by key from the product definition, but their resolvers fetch the currently active PUBLISHED version. The product version itself does not contain component version numbers. A future job created from the same product version can therefore resolve newer component versions.
- Identity is resolved only from the request's optional `identity_key`; it is not defined by the product. Factory identity selection affects the production context independently of the product version.
- The job stores `ResolvedProductionContext.capture(...)` with prompt, recipe, optional identity, output contract, policy, and product snapshots. This preserves the actual resolved versions for that job once created, but does not make the product version immutable across future jobs.
- `ProductionProductControlPlaneService.publish` validates the active recipe against the active output contract and checks that the policy has an active published version; it does not validate product-owned prompt or identity references because neither exists in the product definition. It checks storage access for STORAGE_URI contracts before publication.
- `ControlPlanePage.tsx` exposes recipe key, policy key, output-contract key, audience, and experience. Its summary explicitly says identity and instructions are resolved at job creation and are not required to be bound to the product. “Create draft from this version” creates a version of the same product; it is not a derived product with parent lineage and component diff.

### Execution, retry, and Artifact provenance

- `ProductionJobRunner.run` reads the saved resolved context, verifies the prompt snapshot agrees with legacy prompt key/version/body fields, and uses the pinned recipe when present. Jobs predating context snapshots use their persisted prompt body and legacy `BOOK_TO_TELEGRAM_POST` route; missing historical prompt pins fail rather than being reconstructed from today's active prompt.
- Stale recovery checks for a durable Artifact first, then a saved provider-operation handle. A valid output marks the item complete; a saved provider operation returns the item to pending for resume; no output and no provider handle is held as `PROVIDER_OUTCOME_UNKNOWN` rather than automatically generating again.
- Generic Artifact persistence stores `resolved_context`, the strongest available provenance record for generic artifact paths. This does not prove media duration, dimensions, or semantic content were inspected.

### Video capability evidence

- `alembic/versions/0036_video_artifact_recipe.py` seeds `BOOK_TO_VIDEO_ARTIFACT` v1 with aspect ratio 9:16, resolution 720p, and duration_seconds 5.
- `app/domain/recipes.py` validates `duration_seconds` only as 5, 6, or 8 seconds for `produce_video_artifact` v1. A single clip of 30–60 seconds is not supported by this capability contract.
- `ProduceVideoArtifactCapability.execute` builds its own generic English video prompt from the material, product audience/experience, and recipe `style_instructions`. It does not call `_stage_system_prompt` or use the runner's composed editorial prompt. Consequently, the pinned editorial.drafter body and composed identity are not inputs to this video prompt path. The recipe stage's `style_instructions` is the only explicit video-specific editorial instruction.
- Artifact metadata records requested duration, aspect ratio, resolution, model, and source/title, but inspected code does not probe the resulting media to verify actual duration, dimensions, scene sequence, or audio/text content.
- Railway logs show repeated HTTP 200 GET polling of job `9a1f240a-4e6f-4a69-859a-551b444af087` on 2026-10-13, but logs do not expose response JSON or the provider/item/Artifact rows. The current state of that job and its relation to material `97befce9-1fa8-467c-acbf-fd913ba2535f` remain unverified, not inferred from polling logs.

## Confirmed gap severity

The product-to-run configuration gap is proven by code: product definition cannot select a prompt or identity and stores component keys rather than exact component versions. The video prompt bypass is also proven in capability code. Safe repair requires a compatibility-aware product manifest, version-specific resolvers, Control Plane form/API updates, tests, and a controlled legacy policy. Do not solve this by changing only a default key or silently rewriting production rows.

## Required next implementation slice

1. Introduce a versioned product manifest with prompt and identity references plus exact versions for recipe, policy, and output contract; reuse existing component records.
2. Add resolvers for explicit component versions, including previously published/archived versions referenced by a published product; reject DRAFT or missing versions.
3. Validate the exact manifest and recipe/capability/output-contract/provider compatibility before publishing.
4. Update Control Plane editing to select existing component versions or create drafts; implement derived products as a distinct operation with parent lineage and component diff.
5. Make ordinary factory execution use the product manifest. Keep overrides in a clearly marked experiment path and preserve legacy compatibility for old products/jobs.
6. Design a multi-clip assembly capability if 30–60-second videos are required; do not represent a single 5/6/8-second request as a 30–60-second deliverable.
7. Add tests for pinned versions, missing component rejection, resume/retry, derived-product independence, and video prompt/duration semantics before production acceptance.

## Follow-up implementation evidence — immutable component manifest (2026-10-13)

**Status: implementation branch, not yet merged or operationally accepted.** Main remains at `6f5fdab3bb00bb0f4d11d816c11464343b1b2c27`; candidate branch `feat/immutable-product-component-manifest` is being prepared for PR review.

The candidate implementation now adds these code paths:

- `ProductionProductDefinition` can represent prompt and identity keys plus a complete `component_versions` manifest. The manifest validator requires concrete version IDs and numbers for prompt, identity, recipe, policy, and output contract, and verifies keys match the product definition.
- Product publication resolves published components once and writes their exact version references into the product version. It does not copy component bodies/definitions into the product.
- `ControlPlaneResolver` has version-ID resolvers that accept previously published versions after they become ARCHIVED, and reject missing or mismatched references.
- Product job creation resolves the component references saved in the published product. A legacy product with no manifest is not silently resolved from current active defaults for a new job; it returns an actionable error. Existing jobs still resume from their saved `resolved_context`.
- A new migration creates a new manifest-backed version for built-in literary post/text products, retaining the previous published versions as archived history. It does not rewrite custom products such as `QUL_WA_LA_TAQUL_VIDEO`; inactive built-in media drafts receive explicit prompt/identity selection fields but remain drafts.
- The Control Plane form now requires prompt and identity selections. The factory is being changed to offer only products with a complete manifest and to display/use the identity pinned by that product.

**Not yet accepted:** CI has not validated this candidate branch. Product derivation/parent lineage and component diffs remain unimplemented. Provider/capability compatibility preflight remains partial. The 30–60-second video requirement is still unresolved; the 5/6/8-second capability limit is not changed here. No provider request or external publication was launched.

