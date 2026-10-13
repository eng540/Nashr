# Nashr Agent Continuation Guide

Read this file first when resuming Nashr work without prior conversation context.

## Source of truth

1. Current code and database/runtime state establish what is implemented; inspect the exact current `main` and deployed release.
2. Accepted ADRs establish architectural intent. Proposed ADRs are not implementation instructions until reviewed/accepted.
3. Architecture maps and contracts explain module ownership and guardrails.
4. Operations logs record what was actually tested, including limits.
5. Conversation summaries and old task reports are leads, not evidence.

## Read in this order

1. [System map and change policy](../architecture/system-map-and-change-policy.md)
2. [Current architecture baseline](../architecture/current-baseline.md)
3. [Target architecture](../architecture/target-architecture.md)
4. [Shared production engine contract](../architecture/shared-production-engine-contract.md)
5. [Product model and gap audit](../architecture/product-model-and-gap-audit.md)
6. [Product manifest ADR](../architecture/decisions/ADR-001-product-version-manifest.md)
7. [UX experience audit](../ux/experience-audit.md)
8. [UX workflow/function inventory](../ux/workflow-and-function-inventory.md)
9. [UX implementation log](../ux/implementation-log.md)
10. [Product operational status](../operations/product-architecture-status.md)
11. [Foundation roadmap](../architecture/foundation-roadmap.md)

## What is known

- Nashr is an Arabic multi-source/multi-output production platform, not merely a Telegram-post generator.
- Workspaces remain separate: `/console` (source/library), `/posts/workspace` (production/review), `/publishing` (planning/distribution), `/control` (versioned control-plane configuration).
- Current main after PR #129 is `195bf73b0276203f125f7f8a2d45950cf7d9971e` (docs-only merge). Railway production still runs code commit `f0ea7a2c23f9f927e2f0f7cc8c9c9eba810b613c` (#128).
- Products, identities, prompts, recipes, policies, output contracts, and pinned production contexts exist, but existence is not proof of complete product-manifest enforcement across every modality.
- Product definition fields confirmed in code: recipe key, output-contract key, policy key, audience, experience.
- Runner composes pinned identity into the prompt and appends product audience/experience; it validates prompt pin consistency and preserves a legacy prompt-pin path.
- The live state of `QUL_WA_LA_TAQUL_VIDEO` job `9a1f240a-4e6f-4a69-859a-551b444af087` and material `97befce9-1fa8-467c-acbf-fd913ba2535f` remains unverified: Railway logs show repeated GET polling but not response JSON or provider/Artifact rows.

## Non-negotiable guardrails

- Do not send to Telegram or publish externally during acceptance.
- Do not launch duplicate/paid provider work before reconciling existing provider operations and outputs.
- Do not retry unresolved provider outcomes blindly.
- Do not infer deployment from a merge, CI from a Railway status, or output success from an Artifact row alone.
- Do not change schema until the model/repository/API/test audit proves the need.
- Preserve old job pins and workspace boundaries.
- Do not run local tests if the project owner has prohibited them; use CI and report exact evidence.
- Make small, reviewable PRs. Update durable docs and roadmap when status changes.

## Next priority

Implement the proven product-manifest gaps in Product Model and Gap Audit: exact prompt/identity/recipe/policy/output-contract versions in each new product version, version-specific resolvers, strict publish preflight, and explicit derived-product lineage. Preserve compatibility for old products/jobs. Separately design multi-clip assembly if 30–60-second videos are required; current recipe contract supports only 5/6/8-second clips. Before any new video request, obtain read-only access to the exact job/item/provider/Artifact state and reconcile the previous operation.

## Status vocabulary

Use distinct labels: **implemented in code**, **CI passed on exact SHA**, **merged**, **deployed on exact SHA**, **live acceptance verified**. Never collapse them into a single “done”.


## Verified gaps that must not be mistaken for completed work

- `create_production_job` resolves `editorial.drafter` globally before product resolution.
- Product identity is selected through optional request `identity_key`; it is not part of the product definition.
- Product versions reference component keys, while jobs resolve active component versions. Job context snapshots actual versions but cannot make future behavior of the product immutable.
- Video capability constructs a separate prompt from audience/experience and recipe style instructions, bypassing the pinned editorial prompt and composed identity.
- Current video recipe contract allows only 5, 6, or 8 seconds; 30–60 seconds requires a multi-clip assembly architecture, not a constant change.
- PR #127 and PR #129 are merged. Do not repeat the stale status in the older UX implementation log.

## Continuation checkpoint — product manifest work (2026-10-13)

Continue from PR #131 merged and branch `feat/immutable-product-component-manifest`; do not re-audit the project from scratch.

Candidate changes currently on the branch:
1. `app/domain/products.py`: manifest reference validation.
2. `app/application/control_plane.py`: resolve exact component versions by version ID, including archived versions.
3. `app/application/product_control_plane.py`: freeze references at publication.
4. `app/application/production_jobs.py`: new product jobs resolve the published manifest and reject legacy products lacking one; runtime identity overrides are rejected when they conflict with the product.
5. `app/domain/production_context.py`: validates resolved snapshots against manifest references.
6. `alembic/versions/0043_product_component_manifest.py`: creates new manifest-backed versions for built-in post/text products without rewriting their old versions; custom products are not auto-assigned an identity.
7. Control Plane UI and factory changes require prompt/identity selection and consume the product-pinned identity.
8. Integration/E2E assertions exercise pinned component IDs and component-version stability.

Next: inspect the complete diff and CI. Do not merge on a failing or pending CI result. Correct migration downgrade safety if needed, and fix any test failures at their root. Then implement product derivation with parent/version lineage and an explicit component diff in Control Plane, followed by compatibility preflight for capability/output contract/provider and a documented, measurable video-duration decision. Keep Telegram/external publication disabled in tests. Do not mark ADR-001 Accepted until all acceptance gates are met; do not claim Railway deployment from GitHub CI.

## Stacked derivation work (2026-10-13)

The current follow-on branch is `feat/product-derivation-lineage`, stacked on `feat/immutable-product-component-manifest` (PR #132). It adds:
- nullable product parent and source-version foreign keys in migration `0044_product_derivation_lineage`;
- a derive API from a published/archived manifest-backed version;
- draft preservation of unchanged component references, with partial references allowed only in drafts;
- publication that resolves preserved references by exact ID and resolves only changed/missing references from the selected key's active published version;
- a Control Plane derivation dialog, parent/version provenance, and component diff display;
- an integration test for independent source/derived definitions and shared references.

Do not open/merge this as a main-based PR until PR #132 has passed CI and merged. The stacked branch itself still needs CI and migration review; a Control Plane Playwright test now covers the derive flow and exact component reuse. The product-version repository join must use the explicit `product_id` foreign key because lineage adds a second foreign-key path between product and version tables. Do not mark ADR-001 Accepted. Continue next with capability/provider compatibility preflight and the video duration decision; do not generate or publish a real video.

