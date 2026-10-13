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
