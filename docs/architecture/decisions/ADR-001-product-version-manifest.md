# ADR-001: Product Version as an Explicit Production Manifest

- **Status:** Proposed — pending full model/API audit and implementation review
- **Date:** 2026-10-13
- **Decision scope:** Product configuration and production context
- **Related evidence:** `product-model-and-gap-audit.md`; `app/domain/products.py`; `app/domain/production_context.py`; `app/application/production_jobs.py`; PR #123 and PR #124.

## Context

Nashr now has versioned products and a versioned `ResolvedProductionContext`. The product definition currently names recipe, output contract, and policy by key, plus audience and experience. Prompt and identity are pinned separately in the runtime context. The product-to-context integration exists, but the available evidence does not yet establish that every published product fully declares every required component or that all modalities consume all fields consistently.

## Options considered

1. Continue resolving components from active/global defaults at job start.
2. Require every product to duplicate all component records.
3. Treat the published product version as an immutable manifest of explicit references to immutable component versions, reusing shared component versions where appropriate.
4. Keep legacy behavior indefinitely without an explicit compatibility boundary.

## Proposed decision

Adopt option 3 as the target. Product versions reference concrete published component versions needed by that product; components may be reused. Draft edits and newly published component versions do not alter existing product versions or pinned jobs. Product derivation creates an independent product lineage record and an explicit component diff, without automatically cloning every component.

For legacy products/jobs, use a documented compatibility path based on their existing persisted pins; never silently resolve an old run from today's active defaults.

## Consequences

**Positive:** reproducible configuration, explainable artifacts, safer retries/resume, reusable components, independent product variants.

**Costs/risks:** migration/compatibility design, more preflight validation, explicit handling of missing components, and a need to distinguish product draft changes from published versions.

## Alternatives rejected

- Implicit active-version resolution as the lasting contract: can change behavior without changing the product version.
- Clone every component on derivation: duplicates reusable assets and creates needless maintenance.
- Rewrite all legacy records immediately: risks breaking provenance and old job resume semantics.

## Required before marking Accepted

- Full audit of models, migrations, repositories, API and frontend contracts.
- Tests for immutable published versions, explicit missing-component failures, independent derived products, shared component reuse, and old job resume/retry.
- Product/recipe/contract/provider compatibility checks.
- Video duration acceptance from request through actual output metadata.
- Review and approval of any required schema migration.
- PR and CI evidence; production evidence recorded separately.

This ADR records the intended decision, not proof that it is implemented.

## Implementation status update (2026-10-13)

**ADR status remains Proposed.** The branch `feat/immutable-product-component-manifest` contains a candidate implementation, but it is not merged and is not evidence of acceptance.

Candidate evidence to review in PR:

- Product definitions carry exact version references for prompt, identity, recipe, policy, and output contract.
- Publication freezes component version IDs/numbers into the product version.
- Job creation resolves the frozen references, including archived versions, and the resolved context validates that each pinned component matches the manifest.
- The factory does not allow an ordinary runtime identity selection to override the product's identity.
- A compatibility migration creates new manifest-backed versions for built-in post/text products rather than rewriting their historical versions; custom products are not auto-assigned a generic identity.

Acceptance requirements still open: CI on the candidate branch; proof of safe legacy resume/retry; product derivation lineage and explicit diffs; full recipe/contract/capability/provider compatibility preflight; and video duration acceptance based on actual output evidence. Do not change this ADR to Accepted until those gates are reviewed and the implementation is merged. Production deployment and operational evidence must be recorded separately.

## PR #132 implementation checkpoint (2026-10-13)

Status remains Proposed. The candidate implements explicit immutable references for prompt, identity, recipe, policy, and output contract and resolves archived versions by exact ID plus version number. It adds migration 0043_product_component_manifest.py, a Control Plane prompt/identity selection path, a factory identity guard, and tests for manifest pinning, prompt replacement, product retry, legacy-product blocking, and runtime identity override.

The migration preserves old product definitions and creates new manifest-backed versions only for selected built-in literary post/text products; custom products are not automatically assigned an identity. Its downgrade is guarded against later product publication and saved job/Artifact references. CI run 38447408736 passed on f55b11af828b24b19abcc113dff4f859b481efd1, but later commits added further guards/tests, so that result does not certify the latest PR head. Review the latest run for the exact head before any merge decision.

Still required before acceptance: latest-head CI, review of migration behavior against realistic production data, explicit product derivation lineage/diffs, complete capability/provider preflight, and measured video-duration acceptance. No Railway migration/deployment or live acceptance has been performed.
